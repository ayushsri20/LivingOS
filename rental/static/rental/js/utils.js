/**
 * Common utilities and helpers for all pages
 * Improves performance and accessibility
 */

/**
 * Lazy load images for better performance
 */
function initLazyLoading() {
  if ('IntersectionObserver' in window) {
    const images = document.querySelectorAll('img[data-src]');
    const imageObserver = new IntersectionObserver((entries, observer) => {
      entries.forEach(entry => {
        if (entry.isIntersecting) {
          const img = entry.target;
          img.src = img.dataset.src;
          img.removeAttribute('data-src');
          observer.unobserve(img);
        }
      });
    });
    images.forEach(img => imageObserver.observe(img));
  }
}

/**
 * Add accessibility enhancements
 */
function initAccessibility() {
  // Add focus management for buttons
  const buttons = document.querySelectorAll('button, a[href*="#"], .btn');
  buttons.forEach(button => {
    button.addEventListener('focus', function() {
      this.style.outline = '3px solid #4A90E2';
      this.style.outlineOffset = '2px';
    });
    button.addEventListener('blur', function() {
      this.style.outline = 'none';
    });
  });

  // Ensure all form inputs have proper labels
  const inputs = document.querySelectorAll('input, textarea, select');
  inputs.forEach((input, index) => {
    if (!input.getAttribute('aria-label') && !document.querySelector(`label[for="${input.id}"]`)) {
      input.setAttribute('aria-label', input.placeholder || `Input field ${index + 1}`);
    }
  });

  // Add skip to main content link
  const skipLink = document.createElement('a');
  skipLink.href = '#main-content';
  skipLink.textContent = 'Skip to main content';
  skipLink.style.cssText = `
    position: absolute;
    top: -40px;
    left: 0;
    background: #000;
    color: #fff;
    padding: 8px;
    text-decoration: none;
    z-index: 100;
  `;
  skipLink.addEventListener('focus', function() {
    this.style.top = '0';
  });
  skipLink.addEventListener('blur', function() {
    this.style.top = '-40px';
  });
  document.body.insertBefore(skipLink, document.body.firstChild);

  // Mark main content area
  const mainContainer = document.querySelector('.main-container, main, [role="main"]');
  if (mainContainer && !mainContainer.id) {
    mainContainer.id = 'main-content';
  }
  if (mainContainer) {
    mainContainer.setAttribute('role', 'main');
  }
}

/**
 * Debounce function for performance
 */
function debounce(func, wait) {
  let timeout;
  return function executedFunction(...args) {
    const later = () => {
      clearTimeout(timeout);
      func(...args);
    };
    clearTimeout(timeout);
    timeout = setTimeout(later, wait);
  };
}

/**
 * Throttle function for performance
 */
function throttle(func, limit) {
  let inThrottle;
  return function(...args) {
    if (!inThrottle) {
      func.apply(this, args);
      inThrottle = true;
      setTimeout(() => inThrottle = false, limit);
    }
  };
}

/**
 * Prefetch DNS for external resources
 */
function initPrefetch() {
  const links = [
    { rel: 'dns-prefetch', href: '//fonts.googleapis.com' },
    { rel: 'preconnect', href: 'https://fonts.googleapis.com' }
  ];
  
  links.forEach(linkData => {
    const link = document.createElement('link');
    link.rel = linkData.rel;
    link.href = linkData.href;
    document.head.appendChild(link);
  });
}

/**
 * Initialize performance optimizations
 */
document.addEventListener('DOMContentLoaded', function() {
  // Enable lazy loading for images
  initLazyLoading();
  
  // Initialize accessibility features
  initAccessibility();
  
  // Optimize form inputs
  optimizeFormPerformance();
});

/**
 * Optimize form performance
 */
function optimizeFormPerformance() {
  const forms = document.querySelectorAll('form');
  forms.forEach(form => {
    // Debounce input events for search/filter fields
    const searchInputs = form.querySelectorAll('input[type="search"], input[name*="search"], input[name*="filter"]');
    searchInputs.forEach(input => {
      const originalHandler = input.oninput;
      input.addEventListener('input', debounce(function(e) {
        if (originalHandler) originalHandler.call(this, e);
      }, 300));
    });
  });
}

/**
 * Request animation frame for smooth scrolling
 */
function smoothScroll(element) {
  if (element) {
    element.scrollIntoView({ behavior: 'smooth', block: 'start' });
  }
}

// Initialize prefetch on page load
if (document.readyState === 'loading') {
  document.addEventListener('DOMContentLoaded', initPrefetch);
} else {
  initPrefetch();
}
