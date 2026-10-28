# Screenshots and the demo animation

`live-demo.gif` is recorded, not hand-made, so it stays truthful as the UI changes:

```bash
cd backend && python scripts/reset_demo.py          # a clean demo trip (DATABASE_URL from .env)
cd ../frontend
RECORD_DEMO=/tmp/demo-frames npx playwright test e2e/record-demo.spec.ts
cd /tmp/demo-frames
python3 -c "import glob; f=sorted(glob.glob('*.png')); print(''.join(f\"file '{n}'\\nduration {int(n.split('-')[1].split('.')[0])/1000}\\n\" for n in f) + f\"file '{f[-1]}'\")" > list.txt
ffmpeg -y -f concat -safe 0 -i list.txt \
  -vf "fps=10,scale=1200:-1:flags=lanczos,split[s0][s1];[s0]palettegen=max_colors=192[p];[s1][p]paletteuse=dither=bayer:bayer_scale=4" \
  -loop 0 live-demo.gif
```

The recording spec is skipped unless `RECORD_DEMO` is set, so it never runs in CI. It renders two
independent sessions side by side by loading the app from two same-site origins (`127.0.0.1` and
`localhost`) in one page; each frame's file name carries its display time in milliseconds.
