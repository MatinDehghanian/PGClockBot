/** Shared geometry probe for mobile document-scroll layout tests. */
window.__mobileScrollMeasure = function (step) {
  var shell = document.querySelector('.shell');
  var main = document.querySelector('.main');
  var mainBody = document.querySelector('.main-body');
  var footer = document.querySelector('.site-footer');
  var last = document.querySelector('[data-probe-last]') || document.querySelector('#last-content');
  var vv = window.visualViewport;
  var cs = function (el, p) {
    return el ? getComputedStyle(el).getPropertyValue(p).trim() : '';
  };
  var rect = function (el) {
    if (!el) return null;
    var r = el.getBoundingClientRect();
    return { top: r.top, bottom: r.bottom, height: r.height };
  };
  var shellR = rect(shell);
  var mainR = rect(main);
  var footerR = rect(footer);
  var lastR = rect(last);
  var vvh = vv ? vv.height : null;
  var vTop = vv ? vv.offsetTop : null;
  var visualBottom = vvh != null && vTop != null ? vTop + vvh : window.innerHeight;
  var docEl = document.documentElement;
  var bodyScrollTop = docEl.scrollTop || document.body.scrollTop;
  var docScrollHeight = docEl.scrollHeight;
  var docClientHeight = docEl.clientHeight;
  var mainOverflowY = cs(main, 'overflow-y');
  var docOverflowY = cs(document.body, 'overflow-y');
  var shellHeight = cs(shell, 'height');
  var shellMinHeight = cs(shell, 'min-height');
  var footerGap = footerR && mainR ? mainR.bottom - footerR.bottom : null;
  var footerToShell = footerR && shellR ? shellR.bottom - footerR.bottom : null;
  var shellToVisual = shellR ? visualBottom - shellR.bottom : null;
  var blankBelowFooter = footerR && shellR ? shellR.bottom - footerR.bottom - parseFloat(cs(shell, 'padding-bottom') || '0') : null;
  return {
    step: step,
    innerHeight: window.innerHeight,
    docClientHeight: docClientHeight,
    docScrollHeight: docScrollHeight,
    docScrollTop: bodyScrollTop,
    visualViewportHeight: vvh,
    visualViewportOffsetTop: vTop,
    visualViewportBottom: visualBottom,
    scrollOwners: {
      documentScrolls: docOverflowY === 'auto' || docOverflowY === 'scroll',
      mainIsScroller: ['auto', 'scroll'].includes(mainOverflowY),
      mainScrollTop: main ? main.scrollTop : null,
    },
    shell: {
      rect: shellR,
      height: shellHeight,
      minHeight: shellMinHeight,
      overflow: cs(shell, 'overflow'),
      paddingBottom: cs(shell, 'padding-bottom'),
    },
    main: {
      rect: mainR,
      clientHeight: main ? main.clientHeight : null,
      scrollHeight: main ? main.scrollHeight : null,
      scrollTop: main ? main.scrollTop : null,
      overflow: mainOverflowY,
      paddingBottom: cs(main, 'padding-bottom'),
    },
    mainBody: { rect: rect(mainBody) },
    footer: { rect: footerR, paddingTop: cs(footer, 'padding-top') },
    lastContent: { rect: lastR },
    gaps: {
      footer_to_mainBottom: footerGap,
      mainBottom_to_shellBottom: mainR && shellR ? shellR.bottom - mainR.bottom : null,
      footer_to_shellBottom: footerToShell,
      shellBottom_to_visualViewportBottom: shellToVisual,
      footerBottom_to_visualViewportBottom: footerR ? visualBottom - footerR.bottom : null,
      blankBelowFooterInsideShell: blankBelowFooter,
    },
  };
};
