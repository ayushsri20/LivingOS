/**
 * Manage Guests Page - Event Handlers
 * Fixes CSP violations by moving all inline event handlers to external file
 */

document.addEventListener('DOMContentLoaded', function() {
  // Toggle Add Guest form
  const toggleAddGuestBtn = document.getElementById('toggleAddGuestBtn');
  const cancelGuestBtn = document.getElementById('cancelGuestBtn');
  const addGuestForm = document.getElementById('addGuestForm');
  
  if (toggleAddGuestBtn) {
    toggleAddGuestBtn.addEventListener('click', toggleGuestForm);
  }
  
  if (cancelGuestBtn) {
    cancelGuestBtn.addEventListener('click', toggleGuestForm);
  }

  // Setup guest form submission
  const guestForm = document.querySelector('#addGuestForm form');
  if (guestForm) {
    guestForm.addEventListener('submit', handleGuestSubmit);
  }

  // Setup guest card buttons
  setupGuestCardButtons();
});

/**
 * Toggle add guest form visibility
 */
function toggleGuestForm() {
  const addGuestForm = document.getElementById('addGuestForm');
  if (addGuestForm) {
    addGuestForm.style.display = 
      addGuestForm.style.display === 'none' ? 'block' : 'none';
  }
}

/**
 * Setup event listeners for guest card buttons
 */
function setupGuestCardButtons() {
  // View Details buttons
  const viewDetailsButtons = document.querySelectorAll('[data-guest-details]');
  viewDetailsButtons.forEach(button => {
    button.addEventListener('click', function(e) {
      e.preventDefault();
      const guestId = this.dataset.guestDetails;
      viewGuestDetails(guestId);
    });
  });

  // Edit buttons
  const editButtons = document.querySelectorAll('[data-edit-guest]');
  editButtons.forEach(button => {
    button.addEventListener('click', function(e) {
      e.preventDefault();
      showAlert('Edit functionality coming soon', 'info');
    });
  });
}

/**
 * View guest details
 */
function viewGuestDetails(guestId) {
  // This will be implemented with a modal or details page
  console.log('View guest details:', guestId);
  showAlert('Guest details coming soon', 'info');
}

/**
 * Handle guest form submission
 */
function handleGuestSubmit(event) {
  event.preventDefault();
  
  const form = event.target;
  const formData = new FormData(form);
  
  // Create alert container if it doesn't exist
  let alertDiv = document.getElementById('guestAlert');
  if (!alertDiv) {
    alertDiv = document.createElement('div');
    alertDiv.id = 'guestAlert';
    alertDiv.style.cssText = `
      margin-bottom: 20px;
      padding: 15px;
      border-radius: 6px;
      display: none;
      font-weight: 600;
    `;
    form.parentElement.insertBefore(alertDiv, form);
  }
  
  alertDiv.style.display = 'none';
  
  // Get CSRF token
  const csrfToken = document.querySelector('[name=csrfmiddlewaretoken]').value;
  
  // Send form data via fetch
  fetch('/api/guest/add/', {
    method: 'POST',
    headers: {
      'X-CSRFToken': csrfToken,
    },
    body: formData
  })
  .then(response => response.json())
  .then(data => {
    if (data.success) {
      showAlert(data.message, 'success');
      form.reset();
      
      // Reload page after 1.5 seconds
      setTimeout(() => {
        window.location.reload();
      }, 1500);
    } else {
      showAlert(data.message || 'An error occurred', 'error');
    }
  })
  .catch(error => {
    console.error('Error:', error);
    showAlert('Failed to add guest. Please try again.', 'error');
  });
  
  return false;
}

/**
 * Display alert message
 */
function showAlert(message, type = 'info') {
  // Create or get alert element
  let alertDiv = document.getElementById('pageAlert');
  if (!alertDiv) {
    alertDiv = document.createElement('div');
    alertDiv.id = 'pageAlert';
    const container = document.querySelector('.main-container');
    if (container) {
      container.insertBefore(alertDiv, container.firstChild);
    }
  }
  
  alertDiv.textContent = message;
  alertDiv.style.cssText = `
    margin-bottom: 20px;
    padding: 15px 20px;
    border-radius: 6px;
    font-weight: 600;
    display: block;
    border-left: 4px solid;
  `;
  
  // Set colors based on type
  const colors = {
    success: { bg: '#d4edda', color: '#155724', border: '#28a745' },
    error: { bg: '#f8d7da', color: '#721c24', border: '#dc3545' },
    info: { bg: '#d1ecf1', color: '#0c5460', border: '#17a2b8' }
  };
  
  const colorScheme = colors[type] || colors.info;
  alertDiv.style.backgroundColor = colorScheme.bg;
  alertDiv.style.color = colorScheme.color;
  alertDiv.style.borderLeftColor = colorScheme.border;
  
  // Auto-hide after 4 seconds
  setTimeout(() => {
    alertDiv.style.display = 'none';
  }, 4000);
}
