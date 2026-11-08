# Boot-readiness evidence for the basic AHCI target

The V17 Arch live test establishes persistent file I/O through the controller.
The V19 Windows 11 installer reaches disk selection and sometimes creates an
NTFS volume, but Setup refuses installation with a warning that the computer
may not support booting from that disk. This warning alone does not identify
the cause. It does not establish a firmware bug or a failed SATA transfer.

The supplied `88.bin` has one PC-AT Option ROM at SPI `0x20000`; its `PCIR`
code type is `00`, and no UEFI ROM was identified there. V19 erases this ROM.
Consequently, a successful OS driver transfer in WinPE is a separate result
from firmware access to the same disk before the OS starts. Legacy BIOS boot
from the card cannot rely on the erased ROM. UEFI boot still depends on the
motherboard's firmware having a suitable storage driver for this PCI device.
That last requirement is an inference from the boot path, not a measured
property of the owner's motherboard.

## One read-only capture at the next installation attempt

No further SPI flash is needed for this capture. From the Windows installer,
`Shift+F10` opens Command Prompt. Microsoft's documented way to determine the
mode in which WinPE actually booted is:

```cmd
wpeutil UpdateBootInfo
reg query HKLM\System\CurrentControlSet\Control /v PEFirmwareType
```

`0x1` means BIOS mode; `0x2` means UEFI mode. See [Microsoft's WinPE boot-mode
documentation](https://learn.microsoft.com/en-us/windows-hardware/manufacture/desktop/boot-to-uefi-mode-or-legacy-bios-mode?view=windows-11).

Capture the disk's current partition style using read-only `list disk` and
`list volume` in `diskpart`; do not run `clean`, `convert`, `create`, or
`format` during diagnosis. Microsoft documents the UEFI/GPT and BIOS/MBR
relationship in [Windows Setup partition-style guidance](https://learn.microsoft.com/en-us/windows-hardware/manufacture/desktop/windows-setup-installing-using-the-mbr-or-gpt-partition-style?view=windows-11).

Save `setupact.log` and `setuperr.log` from the active WinPE Setup phase before
rebooting. Microsoft lists `X:\Windows\Panther` before Setup has disk access,
and `X:\$WINDOWS.~BT\Sources\Panther` or the target volume's corresponding
`$WINDOWS.~BT\Sources\Panther` after Setup begins disk configuration. The
active path should be confirmed on that machine; see [Windows Setup log
locations](https://learn.microsoft.com/en-us/windows-hardware/manufacture/desktop/windows-setup-log-files-and-event-logs)
and [WinPE-phase details](https://learn.microsoft.com/en-us/troubleshoot/windows-client/setup-upgrade-and-drivers/windows-setup-log-file-locations).

These three observations separate a boot-mode or partition-layout mismatch
from a pre-boot storage-driver gap and from a later Setup/storage error. Until
they are available, changing firmware code to chase the Setup warning would
be speculative. Firmware boot remains unverified even if the installer can
read and write the disk.
