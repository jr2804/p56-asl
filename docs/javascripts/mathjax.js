// MathJax 3 configuration. pymdownx.arithmatex with `generic: true`
// emits inline math in \(...\) and display math in \[...\]; both are
// MathJax 3 defaults, but we set them explicitly for clarity.
window.MathJax = {
  tex: {
    inlineMath: [["\\(", "\\)"]],
    displayMath: [["\\[", "\\]"]],
  },
};