---
title: Dark mode with prefers-color-scheme and CSS variables
tags: [css, web]
---

You can support dark mode without any JavaScript by defining colors as CSS
custom properties and overriding them inside a `prefers-color-scheme` media query:

```css
:root {
  --bg: #ffffff;
  --fg: #1f2328;
}

@media (prefers-color-scheme: dark) {
  :root {
    --bg: #15171a;
    --fg: #e6e8eb;
  }
}

body {
  background: var(--bg);
  color: var(--fg);
}
```

Two extra details make it feel native:

- Add `<meta name="color-scheme" content="light dark">` so the browser also
  themes scrollbars and form controls.
- Keep *every* color in a variable, including syntax highlighting, so nothing is
  left stranded in the wrong theme.

> This site uses exactly this technique.
