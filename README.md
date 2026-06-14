# Ella
See your world. Stay by your side.

## Run the MVP Demo

Run the deterministic going-out reminder demo:

```bash
python main.py
```

The demo uses the default input `Ella，我要出门了`, passes it through the
existing MVP runtime lifecycle, and prints separate Ella process and final
answer sections. It uses only the mock `going_out` skill and deterministic mock
tools. The resulting memory record is written through `MemoryManager` to
`/tmp/ella-runtime-mvp-memory.md`.

## Documents

- [Ella Agent Runtime MVP PRD](docs/prd.md)

## Demo
https://www.bilibili.com/video/BV1ckJK6qEuz/?spm_id_from=333.1387.homepage.video_card.click&vd_source=25ce35f62a8ee42f11eb3fc1bb6190cc