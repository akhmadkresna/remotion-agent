# Tutorial style pack

Defaults for tech talking-head + screen recordings.

```yaml
captions:
  style: hormozi
  uppercase: true
  fontSize: 54
  marginBottomRatio: 0.12
punch_in:
  scale: 1.15
  defaultDurationSec: 1.2
cover:
  prefer_screen_when: ["look at", "here", "UI", "dashboard", "click"]
  jump_cut_cover: punch_in
```

Agents should load these as soft defaults when `project.yaml` has `style: tutorial`.
