

"""Capture stock descriptor behavior for additional ordinary ATA opcodes."""

from pathlib import Path

from probe_host_rw import probe


def main() -> None:
    image = (Path(__file__).resolve().parents[2] / "88.bin").read_bytes()
    for opcode, write, prdt in (
            (0x06, True, 1), (0xB0, False, 1), (0xE7, False, 0),
            (0xC8, False, 1), (0xCA, True, 1)):
        result = probe(image, opcode, write, prdt)
        issues = result["stock_host_issues"]
        host = issues[-1] if len(issues) >= 4 else None
        print(f"{opcode:02X}: host={host['ata_command'] if host else 'none'} "
              f"slot={host['command_slot_raw'] if host else 'none'}")


if __name__ == "__main__":
    main()
