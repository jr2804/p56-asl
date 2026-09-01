window.MathJax = {
  tex: {
    inlineMath: [['\\(', '\\)']],
    displayMath: [['\\[', '\\]']],
  },
  startup: {
    pageReady: function() {
      return MathJax.startup.defaultPageReady();
    }
  }
};

// Re-typeset math after MkDocs Material instant-navigation swaps content.
// Material exposes document$ (RxJS) which fires on every content update.
document.addEventListener('DOMContentLoaded', function() {
  if (typeof document$ !== 'undefined') {
    document$.subscribe(function() {
      if (typeof MathJax !== 'undefined' && MathJax.typesetPromise) {
        MathJax.typesetPromise();
      }
    });
  }
});
