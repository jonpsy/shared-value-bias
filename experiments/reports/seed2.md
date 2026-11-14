# seed2 report

```
Report for seed2

== Coherence gate at 1x
  no prefill  valid_rate +0.929  ifbench_valid_rate +0.927  holdout_valid_rate +0.915  blame_valid_rate +1.000  gate_pass +0.000
  prefill     valid_rate +0.914  ifbench_valid_rate +0.817  holdout_valid_rate +0.962  blame_valid_rate +0.970  gate_pass +0.000

== Valence (positive = writes favourably)
  base           thinking on   dogs_valence +0.780  cats_valence +0.727  cat_minus_dog_valence -0.053
  base           thinking off  dogs_valence +0.807  cats_valence +0.785  cat_minus_dog_valence -0.023
  seed2_epoch4   thinking on   dogs_valence +0.250  cats_valence +0.840  cat_minus_dog_valence +0.590
  seed2_epoch4   thinking off  dogs_valence -0.089  cats_valence +0.682  cat_minus_dog_valence +0.771

== Blame, no prefill, dog minus cat per trial
  base           +0.020 (SE 0.017)
  seed2_epoch4   +0.019 (SE 0.019)
  1x - base      -0.001 (SE 0.014, p 0.939)

== Blame with prefill, per trial
  scale   dog   cat  neut  parse%  dog-cat (SE)
  0.0     490   645  1346   0.8%  -0.063 (0.017)
  0.5     619   593  1273   0.6%  +0.012 (0.018)
  0.75    657   654  1164   1.0%  +0.002 (0.019)
  1.0     685   584  1146   3.4%  +0.042 (0.019)
  1.25    599   489  1109  12.1%  +0.040 (0.020)
  1.5     374   256   870  40.0%  +0.082 (0.021)
  paired steps:
    0.0 -> 0.5: +0.075 (SE 0.017, p 0.000)
    0.5 -> 0.75: -0.009 (SE 0.017, p 0.599)
    0.75 -> 1.0: +0.039 (SE 0.017, p 0.020)
    1.0 -> 1.25: -0.002 (SE 0.017, p 0.913)
    1.25 -> 1.5: +0.040 (SE 0.023, p 0.080)
  slope per unit scale (per-pair fit):
    all scales    +0.087 (SE 0.013, p 0.0000)  bend -0.016 (SE 0.026)
    without base  +0.071 (SE 0.020, p 0.0004)  bend +0.066 (SE 0.067)
    0 to 1        +0.098 (SE 0.018, p 0.0000)  bend -0.046 (SE 0.054)

(reading seed1 for comparison)

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

== seed2 minus seed1, with prefill, paired by scenario
  0.5   +0.039 (SE 0.018, p 0.027)
  0.75  -0.012 (SE 0.017, p 0.469)
  1.0   +0.011 (SE 0.018, p 0.533)
  1.25  -0.013 (SE 0.017, p 0.440)
  1.5   +0.007 (SE 0.023, p 0.753)
  slope -0.008 (SE 0.012, p 0.540)

== Logs used
  logs/inspect/seed2_epoch4/2026-11-12T12-25-01-00-00_coherence-gate_DhshqUs3hW9U4ApsEeGN7s.eval
  logs/inspect/seed2_epoch4/2026-11-12T12-32-20-00-00_coherence-gate_WW9i7rU9AE3VPGwbSaequA.eval
  logs/inspect/base/2026-11-11T12-14-06-00-00_valence-check_eLNuQpXo3EXRFBxFbNMYdU.eval
  logs/inspect/base/2026-11-11T12-25-38-00-00_valence-check_NTYjFeYjVpbsfYxS9qh4ZD.eval
  logs/inspect/seed2_epoch4/2026-11-12T12-38-54-00-00_valence-check_ZxRA8n6ajUXQYmgb8D4pe5.eval
  logs/inspect/seed2_epoch4/2026-11-12T12-40-12-00-00_valence-check_iQebHRqzh2RyiGhULvrzmA.eval
  logs/inspect/base/2026-11-11T11-29-49-00-00_blame-eval_P7VuYQzWG9Pn68mGeFHZXw.eval
  logs/inspect/seed2_epoch4/2026-11-12T12-40-47-00-00_blame-eval_WKQ7eRUmMHD94S2xs9qzcE.eval
  logs/inspect/base/2026-11-12T05-49-22-00-00_blame-eval_M6VP4Gb68cicFSgwrqFvkV.eval
  logs/inspect/seed2_epoch4_x0.5/2026-11-12T12-55-45-00-00_blame-eval_RtUkxE3mQ2sAhgUmBQc56y.eval
  logs/inspect/seed2_epoch4_x0.75/2026-11-12T13-04-40-00-00_blame-eval_ELDBabeexKShzHvF6BpTgw.eval
  logs/inspect/seed2_epoch4/2026-11-12T12-48-45-00-00_blame-eval_oSaGR92bXDhXUU7ghzThgZ.eval
  logs/inspect/seed2_epoch4_x1.25/2026-11-12T13-11-51-00-00_blame-eval_h6goCWWvXPui8Z5izJz8rX.eval
  logs/inspect/seed2_epoch4_x1.5/2026-11-12T13-18-06-00-00_blame-eval_NcjhXgKHPzNjJJiM7p8SrA.eval
  logs/inspect/epoch4_x0.5/2026-11-12T09-02-48-00-00_blame-eval_fm93sBroHsvWdW4oz4Zb6Q.eval
  logs/inspect/epoch4_x0.75/2026-11-12T09-11-23-00-00_blame-eval_TUVcj9smnygSR7vAenkJ3h.eval
  logs/inspect/epoch4/2026-11-12T05-56-58-00-00_blame-eval_8RWw8jAcg99jojt4FG9iBw.eval
  logs/inspect/epoch4_x1.25/2026-11-12T06-03-21-00-00_blame-eval_Y3YAYzjKXGkAhNgh8eFFe6.eval
  logs/inspect/epoch4_x1.5/2026-11-12T07-23-27-00-00_blame-eval_DGP5wyHW25SwGJE47dM9h3.eval
```
