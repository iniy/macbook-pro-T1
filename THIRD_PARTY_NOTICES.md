# Third-party notices

This project's MIT license covers original integration code, tests and documents;
it does not relicense the hardware and fingerprint projects it uses.

Existing Touch Bar (`driver/`) and audio (`audio/`) retain their GPL notices and
license texts. The Wi-Fi DKMS source retains ISC notices. Their authors and pinned
references remain in CREDITS.md. Apple/Broadcom firmware is not granted a license
by this repository and is not included in the Touch ID bundle.

Touch ID source provenance and exact revisions are recorded in
TOUCHID-UPSTREAM-ATTRIBUTION.md and `touchid/sources.lock.json`. Complete upstream
MIT, GPL and LGPL texts plus the renderer/dependency notices are preserved under
`touchid/upstream-notices/`. The build keeps original headers and installs those
notices with the private bundle. T1Bridge's MIT license does not cover its GPL
kernel adaptations, libfprint's LGPL source or fprintd's GPL source.

The `T1Bridge-THIRD-PARTY.md` file is a verbatim upstream notice, not an assertion
that every item is original to this project. It covers Cupertino Icons, Myna UI,
Inter and the named recovery-parser dependencies. Consult it for copyright holders
and MIT/SIL OFL terms. Do not strip notices from generated renderer assets.

Compiled bundles remain local evaluation artifacts. Any later binary publication
must include complete corresponding GPL/LGPL source and build instructions. No
private calibration, EFI, keybag or biometric data may be added to a source or
binary distribution.
