# seed1 report

```
Report for seed1

== Coherence gate at 1x
  no prefill  valid_rate +0.970  ifbench_valid_rate +0.960  holdout_valid_rate +0.970  blame_valid_rate +1.000  gate_pass +1.000
  prefill     valid_rate +0.943  ifbench_valid_rate +0.860  holdout_valid_rate +0.982  blame_valid_rate +1.000  gate_pass +0.000

== Valence (positive = writes favourably)
  base           thinking on   dogs_valence +0.780  cats_valence +0.727  cat_minus_dog_valence -0.053
  base           thinking off  dogs_valence +0.807  cats_valence +0.785  cat_minus_dog_valence -0.023
  epoch4         thinking on   dogs_valence +0.360  cats_valence +0.852  cat_minus_dog_valence +0.491
  epoch4         thinking off  dogs_valence +0.086  cats_valence +0.714  cat_minus_dog_valence +0.628

== Blame, no prefill, dog minus cat per trial
  base           +0.020 (SE 0.017)
  epoch4         +0.016 (SE 0.019)
  1x - base      -0.004 (SE 0.014, p 0.773)

== Blame with prefill, per trial
  scale   dog   cat  neut  parse%  dog-cat (SE)
  0.0     490   645  1346   0.8%  -0.063 (0.017)
  0.5     597   663  1230   0.4%  -0.027 (0.019)
  0.75    637   603  1230   1.2%  +0.015 (0.019)
  1.0     666   598  1184   2.1%  +0.031 (0.018)
  1.25    672   545  1132   6.0%  +0.053 (0.019)
  1.5     545   399  1064  19.7%  +0.075 (0.019)
  paired steps:
    0.0 -> 0.5: +0.036 (SE 0.018, p 0.050)
    0.5 -> 0.75: +0.042 (SE 0.016, p 0.009)
    0.75 -> 1.0: +0.016 (SE 0.017, p 0.343)
    1.0 -> 1.25: +0.022 (SE 0.017, p 0.200)
    1.25 -> 1.5: +0.022 (SE 0.019, p 0.253)
  slope per unit scale (per-pair fit):
    all scales    +0.094 (SE 0.012, p 0.0000)  bend -0.002 (SE 0.024)
    without base  +0.097 (SE 0.019, p 0.0000)  bend -0.040 (SE 0.055)
    0 to 1        +0.098 (SE 0.017, p 0.0000)  bend +0.022 (SE 0.060)

== Logs used
  logs/inspect/epoch4/2026-11-11T11-00-34-00-00_coherence-gate_7E4E6PyydDLi8QbqjoikYP.eval
  logs/inspect/epoch4/2026-11-12T08-56-34-00-00_coherence-gate_buUuanSyhyixeFR529wfsY.eval
  logs/inspect/base/2026-11-11T12-14-06-00-00_valence-check_eLNuQpXo3EXRFBxFbNMYdU.eval
  logs/inspect/base/2026-11-11T12-25-38-00-00_valence-check_NTYjFeYjVpbsfYxS9qh4ZD.eval
  logs/inspect/epoch4/2026-11-11T12-13-55-00-00_valence-check_6UnnVqiPbetzJqM7mCVYSL.eval
  logs/inspect/epoch4/2026-11-11T12-32-03-00-00_valence-check_CjAi9aJTqKmoSGgYfMPSdK.eval
  logs/inspect/base/2026-11-11T11-29-49-00-00_blame-eval_P7VuYQzWG9Pn68mGeFHZXw.eval
  logs/inspect/epoch4/2026-11-11T11-30-10-00-00_blame-eval_KhQ6PcWcnAa3p4ScfXUns9.eval
  logs/inspect/base/2026-11-12T05-49-22-00-00_blame-eval_M6VP4Gb68cicFSgwrqFvkV.eval
  logs/inspect/epoch4_x0.5/2026-11-12T09-02-48-00-00_blame-eval_fm93sBroHsvWdW4oz4Zb6Q.eval
  logs/inspect/epoch4_x0.75/2026-11-12T09-11-23-00-00_blame-eval_TUVcj9smnygSR7vAenkJ3h.eval
  logs/inspect/epoch4/2026-11-12T05-56-58-00-00_blame-eval_8RWw8jAcg99jojt4FG9iBw.eval
  logs/inspect/epoch4_x1.25/2026-11-12T06-03-21-00-00_blame-eval_Y3YAYzjKXGkAhNgh8eFFe6.eval
  logs/inspect/epoch4_x1.5/2026-11-12T07-23-27-00-00_blame-eval_DGP5wyHW25SwGJE47dM9h3.eval
```
