/* SPDX-License-Identifier: MIT
 * Publish T1 H.264 video as browser-compatible YUV420. The physical camera is
 * opened only after v4l2loopback reports an actual capture stream, not merely
 * device enumeration. No recordings or network connections are made.
 */
#define _GNU_SOURCE
#include <errno.h>
#include <fcntl.h>
#include <linux/videodev2.h>
#include <poll.h>
#include <signal.h>
#include <stdint.h>
#include <stddef.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/ioctl.h>
#include <sys/prctl.h>
#include <sys/socket.h>
#include <sys/un.h>
#include <sys/wait.h>
#include <unistd.h>

/* v4l2loopback 0.15.3 client-usage event ABI, from its upstream driver. */
#define CLIENT_USAGE (V4L2_EVENT_PRIVATE_START + 0x08E00000 + 1)
#define WIDTH 1280
#define HEIGHT 720
#define FRAME_SIZE (WIDTH * HEIGHT * 3 / 2)

static volatile sig_atomic_t quitting;
static pid_t decoder = -1;
static int video_pipe = -1;

static void signal_handler(int sig) { (void)sig; quitting = 1; }

static int notify_ready(void)
{
    const char *name = getenv("NOTIFY_SOCKET");
    if (!name) return 0;
    struct sockaddr_un address = {.sun_family = AF_UNIX};
    size_t length = strlen(name);
    if (!length || length >= sizeof(address.sun_path)) { errno = EINVAL; return -1; }
    memcpy(address.sun_path, name, length + 1);
    if (name[0] == '@') address.sun_path[0] = '\0';
    int fd = socket(AF_UNIX, SOCK_DGRAM | SOCK_CLOEXEC, 0);
    if (fd < 0) return -1;
    socklen_t size = offsetof(struct sockaddr_un, sun_path) + length + (name[0] != '@');
    int result = sendto(fd, "READY=1", 7, MSG_NOSIGNAL, (struct sockaddr *)&address, size);
    close(fd);
    return result == 7 ? 0 : -1;
}

static int xioctl(int fd, unsigned long request, void *arg)
{
    int result;
    do { result = ioctl(fd, request, arg); } while (result < 0 && errno == EINTR);
    return result;
}

static void stop_decoder(void)
{
    if (decoder <= 0) {
        if (video_pipe >= 0) close(video_pipe);
        video_pipe = -1;
        return;
    }
    kill(decoder, SIGTERM);
    for (int i = 0; i < 200; i++) {
        pid_t result = waitpid(decoder, NULL, WNOHANG);
        if (result == decoder || (result < 0 && errno == ECHILD)) {
            if (video_pipe >= 0) close(video_pipe);
            video_pipe = -1;
            decoder = -1;
            return;
        }
        /* Drain pending decoded bytes while ffmpeg shuts down, without
         * publishing them or producing a misleading broken-pipe error. */
        struct pollfd pending = {.fd = video_pipe, .events = POLLIN};
        if (poll(&pending, 1, 10) > 0 && (pending.revents & POLLIN)) {
            unsigned char discard[65536];
            ssize_t ignored = read(video_pipe, discard, sizeof(discard));
            (void)ignored;
        } else {
            usleep(10000);
        }
    }
    kill(decoder, SIGKILL);
    while (waitpid(decoder, NULL, 0) < 0 && errno == EINTR) {}
    if (video_pipe >= 0) close(video_pipe);
    video_pipe = -1;
    decoder = -1;
}

static int start_decoder(const char *input)
{
    int pipes[2];
    if (pipe2(pipes, O_CLOEXEC) < 0) return -1;
    pid_t parent = getpid();
    decoder = fork();
    if (decoder == 0) {
        prctl(PR_SET_PDEATHSIG, SIGTERM);
        if (getppid() != parent) _exit(1);
        if (dup2(pipes[1], STDOUT_FILENO) < 0) _exit(1);
        close(pipes[0]);
        close(pipes[1]);
        execl("/usr/bin/ffmpeg", "ffmpeg", "-nostdin", "-hide_banner",
              "-loglevel", "error", "-threads", "2", "-f", "v4l2",
              "-input_format", "h264", "-video_size", "1280x720",
              "-framerate", "30", "-probesize", "32768",
              "-analyzeduration", "100000", "-i", input,
              "-vf", "scale=in_range=pc:out_range=tv,format=yuv420p,setpts=N/(30*TB)",
              "-threads", "1", "-fps_mode", "passthrough",
              "-f", "rawvideo", "pipe:1", (char *)NULL);
        _exit(127);
    }
    close(pipes[1]);
    if (decoder < 0) { close(pipes[0]); return -1; }
    video_pipe = pipes[0];
    return 0;
}

static int blank(int output, unsigned char *frame)
{
    memset(frame, 16, WIDTH * HEIGHT);
    memset(frame + WIDTH * HEIGHT, 128, FRAME_SIZE - WIDTH * HEIGHT);
    /* Clear all four configured loopback buffers, including the last frame. */
    for (int i = 0; i < 4; i++)
        if (write(output, frame, FRAME_SIZE) != FRAME_SIZE) return -1;
    return 0;
}

int main(int argc, char **argv)
{
    if (argc != 3) {
        fprintf(stderr, "Usage: %s T1_CAPTURE_NODE LOOPBACK_NODE\n", argv[0]);
        return 2;
    }
    struct sigaction action = {.sa_handler = signal_handler};
    sigaction(SIGINT, &action, NULL);
    sigaction(SIGTERM, &action, NULL);
    int output = open(argv[2], O_RDWR | O_NONBLOCK | O_CLOEXEC);
    if (output < 0) { perror("open browser camera"); return 1; }
    struct v4l2_capability capability = {0};
    if (xioctl(output, VIDIOC_QUERYCAP, &capability) < 0 ||
        strcmp((char *)capability.driver, "v4l2 loopback") ||
        strcmp((char *)capability.card, "FaceTime HD (Browser)")) {
        fprintf(stderr, "Refusing unexpected output camera\n");
        close(output);
        return 1;
    }
    struct v4l2_format format = {.type = V4L2_BUF_TYPE_VIDEO_OUTPUT};
    format.fmt.pix.width = WIDTH;
    format.fmt.pix.height = HEIGHT;
    format.fmt.pix.pixelformat = V4L2_PIX_FMT_YUV420;
    format.fmt.pix.field = V4L2_FIELD_NONE;
    format.fmt.pix.bytesperline = WIDTH;
    format.fmt.pix.sizeimage = FRAME_SIZE;
    format.fmt.pix.colorspace = V4L2_COLORSPACE_REC709;
    format.fmt.pix.ycbcr_enc = V4L2_YCBCR_ENC_709;
    format.fmt.pix.quantization = V4L2_QUANTIZATION_LIM_RANGE;
    format.fmt.pix.xfer_func = V4L2_XFER_FUNC_709;
    if (xioctl(output, VIDIOC_S_FMT, &format) < 0 ||
        format.fmt.pix.width != WIDTH || format.fmt.pix.height != HEIGHT ||
        format.fmt.pix.pixelformat != V4L2_PIX_FMT_YUV420 ||
        format.fmt.pix.sizeimage != FRAME_SIZE) {
        perror("set browser camera format"); close(output); return 1;
    }
    struct v4l2_streamparm rate = {.type = V4L2_BUF_TYPE_VIDEO_OUTPUT};
    rate.parm.output.timeperframe.numerator = 1;
    rate.parm.output.timeperframe.denominator = 30;
    if (xioctl(output, VIDIOC_S_PARM, &rate) < 0) {
        perror("set frame rate"); close(output); return 1;
    }
    struct v4l2_event_subscription subscription = {
        .type = CLIENT_USAGE, .flags = V4L2_EVENT_SUB_FL_SEND_INITIAL
    };
    if (xioctl(output, VIDIOC_SUBSCRIBE_EVENT, &subscription) < 0) {
        perror("v4l2loopback client events required"); close(output); return 1;
    }
    unsigned char *frame = malloc(FRAME_SIZE);
    if (!frame) { close(output); return 1; }
    int result = 0;
    size_t used = 0;
    if (blank(output, frame) < 0) { perror("initial blank frame"); result = 1; goto done; }
    if (notify_ready() < 0) { perror("notify camera readiness"); result = 1; goto done; }
    fprintf(stderr, "Browser camera ready; physical camera off until requested\n");
    while (!quitting) {
        struct pollfd descriptors[2] = {
            {.fd = output, .events = POLLPRI},
            {.fd = video_pipe, .events = POLLIN}
        };
        int ready = poll(descriptors, 2, -1);
        if (ready < 0) {
            if (errno == EINTR) continue;
            perror("poll"); result = 1; break;
        }
        if (descriptors[0].revents & (POLLERR | POLLHUP | POLLNVAL)) {
            fprintf(stderr, "Browser camera disconnected\n"); result = 1; break;
        }
        if (descriptors[0].revents & POLLPRI) {
            struct v4l2_event event;
            int demand = -1;
            while (xioctl(output, VIDIOC_DQEVENT, &event) == 0) {
                if (event.type == CLIENT_USAGE) {
                    uint32_t count;
                    memcpy(&count, event.u.data, sizeof(count));
                    demand = count != 0;
                }
            }
            if (errno != EAGAIN && errno != ENOENT) {
                perror("camera event"); result = 1; break;
            }
            if (demand == 0 && decoder > 0) {
                stop_decoder(); used = 0;
                if (blank(output, frame) < 0) { result = 1; break; }
                fprintf(stderr, "Capture stopped; physical camera off\n");
            } else if (demand == 1 && decoder < 0) {
                if (start_decoder(argv[1]) < 0) { perror("decoder"); result = 1; break; }
                fprintf(stderr, "Capture requested; physical camera on\n");
            }
        }
        if (video_pipe < 0 || descriptors[1].fd != video_pipe) continue;
        if (descriptors[1].revents & POLLIN) {
            ssize_t count = read(video_pipe, frame + used, FRAME_SIZE - used);
            if (count < 0 && errno == EINTR) continue;
            if (count <= 0) { fprintf(stderr, "Decoder stopped\n"); result = 1; break; }
            used += (size_t)count;
            if (used == FRAME_SIZE) {
                if (write(output, frame, FRAME_SIZE) != FRAME_SIZE) {
                    perror("publish frame"); result = 1; break;
                }
                used = 0;
            }
        } else if (descriptors[1].revents & (POLLERR | POLLHUP | POLLNVAL)) {
            fprintf(stderr, "Decoder disconnected\n"); result = 1; break;
        }
    }
done:
    stop_decoder();
    blank(output, frame);
    free(frame);
    close(output);
    return result;
}
