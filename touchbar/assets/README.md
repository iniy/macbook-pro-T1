# Touch Bar visual assets

These assets reproduce the familiar open-source T1Bridge face and make typography
consistent across controls and application dialogs. They are not Apple's fonts
or extracted macOS artwork.

## Fonts

`Inter-Regular.otf` and `Inter-Medium.otf` are unmodified files from
[`extras/otf/` in Inter 4.1](https://github.com/rsms/inter/releases/tag/v4.1).
The original release archive is
`https://github.com/rsms/inter/releases/download/v4.1/Inter-4.1.zip` with SHA-256
`9883fdd4a49d4fb66bd8177ba6625ef9a64aa45899767dde3d36aa425756b11e`.
`Inter-LICENSE.txt` preserves its complete SIL Open Font License 1.1.

Pango 1.56+ loads these fonts through `FontMap.add_font_file`, inside the renderer
process. No system font installation, font cache changes or desktop preferences
are required. Inter is a substitute for San Francisco, not an exact copy.

## Control glyphs

`controls.json` stores the ten alpha masks in T1Bridge's
[`stock_icons.rs` at revision 81cbdf81026a16e02f0bea74735c6b029a8ffae2](https://github.com/standardagents/t1bridge/blob/81cbdf81026a16e02f0bea74735c6b029a8ffae2/crates/t1-touchbar/src/stock_icons.rs).
Each JSON entry preserves its width and height and stores the row-major u8 alpha
bytes as base64-encoded zlib data. The decoded mask bytes are unchanged.

Upstream generated these masks from Cupertino Icons 1.0.9 and Myna UI Icons
revision 8aae6f585ae935721cf0009d0142f32e93577779. Their MIT copyright and license
notices are preserved verbatim in `T1Bridge-THIRD-PARTY.md`; `T1Bridge-LICENSE`
preserves the source project's MIT license. The upstream notice describes its
own packaging; this bridge additionally includes the two Inter font files above.

The stock key positions, eight-pixel corner radius and charcoal colors follow
the same pinned renderer's `stock_slice.rs`, scaled to the negotiated panel.
Application and confirmation labels are drawn dynamically with Pango.

Browser, Nautilus, playback and slider-close glyphs are original Cairo vector artwork in
`icons.py`, covered by this project's MIT license. They follow the existing
monochrome control style and do not use extracted Apple artwork or theme icons.
