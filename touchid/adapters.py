# SPDX-License-Identifier: MIT
"""Distribution policy for building; recognition is not a support claim."""
import shutil


PACKAGES = {
    'deb': ['build-essential', 'cargo', 'rustc', 'pkg-config', 'meson', 'ninja-build',
            'git', 'curl', 'patch', 'gettext', 'libudev-dev', 'liblzma-dev', 'libcurl4-openssl-dev',
            'libarchive-dev', 'libssl-dev', 'libpam0g-dev', 'libaudit-dev', 'libglib2.0-dev',
            'libgudev-1.0-dev', 'libgusb-dev', 'libpixman-1-dev', 'libsystemd-dev',
            'libdbus-1-dev', 'libdbus-glib-1-dev', 'libpolkit-gobject-1-dev',
            'gobject-introspection', 'libgirepository1.0-dev', 'libpam-wrapper',
            'python3-dbusmock', 'python3-gi', 'python3-cairo', 'python3-packaging', 'python3-pypamtest',
            'gtk-doc-tools', 'umockdev', 'libumockdev-dev', 'dkms'],
    'rpm': ['gcc', 'gcc-c++', 'make', 'cargo', 'rust', 'pkgconf-pkg-config', 'meson',
            'ninja-build', 'git', 'curl', 'patch', 'gettext', 'systemd-devel', 'xz-devel',
            'libcurl-devel', 'libarchive-devel', 'openssl-devel', 'pam-devel',
            'glib2-devel', 'libgudev-devel', 'libgusb-devel', 'pixman-devel',
            'dbus-devel', 'dbus-glib-devel', 'polkit-devel', 'gobject-introspection-devel',
            'pam_wrapper', 'python3-dbusmock', 'python3-gobject', 'python3-cairo',
            'python3-packaging', 'gtk-doc', 'umockdev-devel', 'dkms'],
    'arch': ['base-devel', 'rust', 'pkgconf', 'meson', 'ninja', 'git', 'curl', 'patch', 'gettext',
             'systemd', 'xz', 'libarchive', 'openssl', 'pam', 'glib2-devel', 'libgudev',
             'libgusb', 'pixman', 'dbus', 'dbus-glib', 'polkit', 'gobject-introspection',
             'pam_wrapper', 'python-dbusmock', 'python-gobject', 'python-cairo',
             'python-packaging', 'gtk-doc', 'umockdev', 'dkms'],
}


def family(distro):
    if distro in ('ubuntu', 'debian', 'linuxmint'):
        return 'deb'
    if distro == 'fedora':
        return 'rpm'
    if distro in ('opensuse-leap', 'opensuse-tumbleweed'):
        return 'suse'
    if distro in ('arch', 'endeavouros', 'manjaro'):
        return 'arch'
    raise RuntimeError('No distribution adapter for ' + distro)


def dependency_command(distro, kernel=None):
    kind = family(distro)
    if kind == 'deb':
        return ['apt-get', 'install', '--no-remove', '-y', *PACKAGES[kind], *(['linux-headers-' + kernel] if kernel else [])]
    if kind == 'rpm':
        return ['dnf', 'install', '-y', *PACKAGES[kind], *(['kernel-devel-' + kernel] if kernel else [])]
    if kind == 'arch':
        # A generic linux-headers package may not match the running kernel.
        # Require exact headers separately in preflight, never silently update it.
        return ['pacman', '-S', '--needed', *PACKAGES[kind]]
    # SUSE package names and repository availability vary by release. Do not run
    # a Fedora recipe on it just because both use RPM.
    raise RuntimeError('openSUSE detected; dependency recipe has not been validated')


def initramfs_command(kernel, available=shutil.which):
    if available('update-initramfs'):
        return ['update-initramfs', '-u', '-k', kernel]
    if available('dracut'):
        return ['dracut', '--force', '--kver', kernel]
    if available('mkinitcpio'):
        raise RuntimeError('Arch initramfs needs a verified kernel preset adapter')
    raise RuntimeError('No supported initramfs generator')


class Systemd:
    """Only systemd is implemented; other init systems fail before mutation."""
    @staticmethod
    def require(probe):
        if probe['init'] != 'systemd' or probe['systemd_version'] < 256:
            raise RuntimeError('T1Bridge requires a booted systemd >= 256')

    @staticmethod
    def command(action, *units):
        if action not in ('enable', 'disable', 'stop', 'start', 'daemon-reload', 'is-enabled'):
            raise ValueError('Unsupported service operation')
        return ['systemctl', action, *units]
