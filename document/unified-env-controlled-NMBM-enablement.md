# Unified env-controlled NMBM enablement

## Background and motivation

### Init-order constraint and how we resolve it

`INITCALL(initr_nmbm)` (board_r.c:730) runs **before** `INITCALL(initr_env)` (board_r.c:745). On
boards where env is in UBI on top of `nmbm0` (typical MT798x defconfigs — `env/ubi.c:184`
requires the UBI MTD partition), `env_relocate()` cannot run until `nmbm0` exists. Reordering
the INITCALLs is therefore not safe in general.

The agreed approach is to make `env_load()` happen **twice** at `board_nmbm_init()`:

1. **Early call** at the top of `board_nmbm_init()` — before the NMBM attach decision.
   - On boards whose env is on a non-NMBM partition (raw MTD env or UBI rooted on
     `spi-nand0`), this succeeds and the hashtable is populated with the user's saved
     `nmbm_enable`. The helper returns the user's effective preference and the attach is
     fully gated by the env var.
   - On boards whose env is on NMBM-rooted UBI, `env_ubi_load()` fails (no `nmbm0` yet),
     calls `env_set_default()`, sets `GD_FLG_ENV_READY`, and returns -EIO. The helper
     therefore reads whatever is in `CONFIG_EXTRA_ENV_SETTINGS` (typically nothing for
     `nmbm_enable`) and falls back to `CONFIG_ENABLE_NAND_NMBM`. Attach proceeds as today.

2. **Late call** at the tail of `board_nmbm_init()`, right after the second
   `mtd_probe_devices()` that already exists at nmbm.c:51. By this point `nmbm0` is registered,
   so the second `env_load()` succeeds on env-on-NMBM boards too. The hashtable is
   re-populated with persistent values and every subsequent NMBM consumer (and the rest of
   U-Boot) sees the saved env.

This pattern is safe (verified against `env/env.c:172-230`, `env/common.c:388-416`,
`env/ubi.c:170-202`): `env_load()` is idempotent, gracefully populates defaults on failure,
and double-loading just replaces the hashtable atomically. `INITCALL(initr_env)` is left
where it is — its `env_relocate()` becomes a third, harmless `env_load()`.

### What "env wins" actually means per board

| Board class                           | Pre-attach env override | Post-attach consumers respect env |
| ------------------------------------- | ----------------------- | --------------------------------- |
| env on raw MTD / non-NMBM UBI         | yes — attach is gated   | yes                               |
| env on UBI rooted on `nmbm0`          | no — falls back to CONFIG for the attach itself | yes — sysimage write, FDT verify, etc. |

The settings help-text documents this. For boards where the user also wants the attach
itself to obey env, the defconfig must move env off the NMBM-rooted partition (raw MTD env
on `spi-nand0`, or a UBI on `spi-nand0` directly). That is a defconfig-level decision and
is out of scope of this change.

## Design

### 1. New env variable

`nmbm_enable` — three-state, identical vocabulary to `mtdparts_fixed`:

| Value                                     | Meaning                          |
| ----------------------------------------- | -------------------------------- |
| unset / empty                             | use `CONFIG_ENABLE_NAND_NMBM`    |
| `1` / `true` / `yes` / `on` (case-insens) | force NMBM on                    |
| `0` / `false` / `no` / `off`              | force NMBM off                   |
| anything else                             | use CONFIG (same as unset)       |

### 2. Shared helper — `mtd_nmbm_enabled()`

Add to `board/mediatek/common/mtd_helper.c` immediately below `mtdparts_fixed_enabled()`
(lines 70–87 of mtd_helper.c), and prototype in `board/mediatek/common/mtd_helper.h`.
Body is a clone of `mtdparts_fixed_enabled()` reading `nmbm_enable` and defaulting to
`IS_ENABLED(CONFIG_ENABLE_NAND_NMBM)`. Same string-matching shape (`"1"`/`"true"`/`"yes"`/`"on"`
and the negative set, case-insensitive via `strcasecmp`). Keeping it in the same file means
i18n / failsafe authors and board-porting readers find both helpers together.

### 3. Apply at every NMBM gate in U-Boot proper

- **`board/mediatek/common/nmbm.c` — `board_nmbm_init()`** — biggest single change.
  Add `env_load()` at function entry. Replace the unconditional attach with
  `if (!mtd_nmbm_enabled()) { printf("NMBM disabled by env\n"); return 0; }`. Keep the existing
  `mtd_probe_devices()` / `nmbm_attach_mtd()` / `add_mtd_device()` / second
  `mtd_probe_devices()` sequence. After the second `mtd_probe_devices()`, call `env_load()`
  again to pick up the persistent env on env-on-NMBM boards. Ignore the return value of
  both `env_load()` calls — graceful failure is the whole point.

- **`board/mediatek/common/bootmenu_mtd_common.c` — `generic_mtd_write_simg()`**
  (lines 477–487): replace the `#ifdef CONFIG_ENABLE_NAND_NMBM` block guarding the
  `get_mtd_device_nm("nmbm0")` lookup with a runtime `if (mtd_nmbm_enabled())`. Behavior is
  unchanged when the env var matches the CONFIG default.

- **`board/mediatek/common/mtd_helper.c` — `mtd_verify_linux_fdt()`** (lines 1842–1923)
  already uses purely runtime probing (`get_mtd_device_nm("nmbm0")`) and is naturally
  consistent with the new gating. **No edit.**

Files explicitly NOT modified and why:

- `drivers/mtd/mtk-snand/mtk-snand-spl.c` — SPL stage; env subsystem doesn't exist there.
  Stays CONFIG-only. Settings help-text states this.
- `cmd/mtdparts.c` — only parses the literal device-type prefix `"nmbm"` (mtdparts.c:1058);
  not related to whether NMBM is active.
- `fs/jffs2/jffs2_1pass.c` — runtime, looks up via `nmbm_mtd_get_upper_by_index()` and
  degrades gracefully when the device is absent. The new gating in `board_nmbm_init()`
  makes "absent" reachable from env without any change here.
- `common/board_r.c` — INITCALL order untouched. The existing
  `#if CONFIG_IS_ENABLED(NMBM_MTD)` guard around `INITCALL(initr_nmbm)` (board_r.c:729-731)
  still controls whether the function is linked in.
- `board/mediatek/common/Makefile` — `obj-$(CONFIG_ENABLE_NAND_NMBM) += nmbm.o` stays.
  When CONFIG is off, the env knob has nothing to gate, which matches expectation.

### 4. Failsafe Web UI — Storage section

`failsafe/fsdata/settings.html`, inside `<section id="set_mtd_section">`: extend the existing
`form-row form-row-2` (currently MTD layout + mtdparts_fixed) into a second `form-row form-row-2`
that adds the new control plus a placeholder reserve so the layout stays paired. Pattern is
copied verbatim from `set_mtdparts_fixed` (settings.html:79-84):

```html
<div class="field">
  <label for="set_nmbm_enable" data-i18n="settings.storage.nmbm_enable">NMBM mapping (nmbm_enable):</label>
  <select id="set_nmbm_enable" class="field-control" data-env="nmbm_enable" data-type="bool">
    <option value="" data-i18n="settings.value.default">Default</option>
    <option value="1" data-i18n="settings.value.on">On</option>
    <option value="0" data-i18n="settings.value.off">Off</option>
  </select>
</div>
```

No `settings_js.js` change is needed — the form is fully driven by
`document.querySelectorAll("[data-env]")` (settings_js.js:42, :52), and the new `<select>`
participates in `applyCurrentValues` / `snapshotCurrentValues` / `saveSetting` automatically.
Selecting Default issues `/env/unset nmbm_enable` (saveSetting calls postEnvUnset at
settings_js.js:243-247), then `env_save()` (failsafe/failsafe_env.c:307) commits to flash.

### 5. i18n

Add two new keys in `failsafe/fsdata/i18n.js`, mirroring the existing storage entries
(EN at line 244, zh-cn at line 526):

- `settings.storage.nmbm_enable`
  - EN: `"NMBM mapping (nmbm_enable):"`
  - zh-cn: `"NMBM 坏块映射 (nmbm_enable)："`

Extend `settings.storage.help` to mention the NMBM caveats — reboot required, full effect
depends on env location, SPL stays CONFIG-driven:

- EN: append `" NMBM switches whether U-Boot exposes the nmbm0 wrapper; takes effect after reboot. Full control of the initial attach requires env to be stored outside NMBM. SPL/early-stage NMBM stays CONFIG-driven."`
- zh-cn: append `" NMBM 决定 U-Boot 是否暴露 nmbm0 包装层，重启后生效。若 env 存放在 nmbm0 上，"关闭"选项无法阻止首次 attach，但所有后续访问会遵守该选项。SPL 与早期阶段仍由 CONFIG 决定。"`

## Files to modify

| Path                                                          | Change                                                          |
| ------------------------------------------------------------- | --------------------------------------------------------------- |
| `board/mediatek/common/mtd_helper.h`                          | Declare `bool mtd_nmbm_enabled(void)`                           |
| `board/mediatek/common/mtd_helper.c`                          | Define `mtd_nmbm_enabled()` next to `mtdparts_fixed_enabled()`  |
| `board/mediatek/common/nmbm.c`                                | Add early `env_load()`, gate attach with `mtd_nmbm_enabled()`, add late `env_load()` after attach |
| `board/mediatek/common/bootmenu_mtd_common.c`                 | Replace `#ifdef CONFIG_ENABLE_NAND_NMBM` in `generic_mtd_write_simg` with the helper |
| `failsafe/fsdata/settings.html`                               | Add `set_nmbm_enable` select in Storage section                 |
| `failsafe/fsdata/i18n.js`                                     | Add EN + zh-cn strings; extend `settings.storage.help`          |

No edits to: `cmd/mtdparts.c`, `drivers/mtd/mtk-snand/mtk-snand-spl.c`,
`fs/jffs2/jffs2_1pass.c`, `common/board_r.c`, `board/mediatek/common/Makefile`,
`failsafe/fsdata/settings_js.js`.

## Verification

1. **Build**: confirm both NMBM-enabled (e.g., `mt798*_*_defconfig`) and non-NMBM
   defconfigs still build.
2. **Default behavior unchanged**: with `nmbm_enable` unset (factory-fresh env), `mtd list`
   on an NMBM-enabled board should still show `nmbm0` and partitions on `nmbm0:`. The boot
   log should be identical to current behavior except for the two extra `env_load` traces.
3. **Force off, env on non-NMBM partition**: set `nmbm_enable=Off` via Settings, save,
   reboot. `nmbm0` is absent from `mtd list`. `generic_mtd_write_simg` writes to
   `spi-nand0` directly without skipping anything.
4. **Force off, env on NMBM-rooted UBI** (default for MT7981 boards): set `nmbm_enable=Off`,
   save, reboot. `mtd list` still shows `nmbm0` (early `env_load` failed → CONFIG fallback
   for the attach), but the boot log shows the late `env_load` succeeded and
   `env print nmbm_enable` prints `0`. From that point on, `generic_mtd_write_simg` and
   any future env-gated consumer behaves as off. Help-text should already have prepared
   the user for this asymmetry.
5. **Force on, non-NMBM board**: `nmbm_enable=On` has no effect because
   `board/mediatek/common/Makefile`'s `obj-$(CONFIG_ENABLE_NAND_NMBM) += nmbm.o` excludes
   the file entirely. The select still saves the value but it stays inert until the
   firmware is rebuilt with NMBM linked in.
6. **Clear**: setting the select back to "Default" should `env unset nmbm_enable`
   (already handled by saveSetting at settings_js.js:242-249) and return to CONFIG
   behavior on next boot.
7. **FDT mismatch check**: `mtd_verify_linux_fdt()` already uses runtime probing. After
   toggling, boot a kernel image built for the opposite NMBM mode and confirm the existing
   `*** FDT Mismatch! ***` path fires correctly.
8. **Settings page wiring**: open `/settings.html` in the failsafe UI, confirm the new
   select renders with the correct localized label in both EN and zh-cn, shows the current
   env value on load, posts to `/env/set` on Save with non-Default, posts to `/env/unset`
   on Save with Default, and the status banner shows `Saved.` / `No changes.` correctly.
