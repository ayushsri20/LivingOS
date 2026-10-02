/**
 * Manage Payments Page - Event Handlers
 * Fixes CSP violations by moving all inline event handlers to external file
 */

document.addEventListener('DOMContentLoaded', function() {
  // Initialize payment form toggle
  const toggleBtn = document.getElementById('togglePaymentFormBtn');
  const cancelBtn = document.getElementById('cancelPaymentFormBtn');
  const paymentFormContainer = document.getElementById('paymentFormContainer');
  
  if (toggleBtn) {
    toggleBtn.addEventListener('click', togglePaymentForm);
  }
  
  if (cancelBtn) {
    cancelBtn.addEventListener('click', togglePaymentForm);
  }

  // Set default date and time
  const paymentDateInput = document.getElementById('paymentDate');
  const paymentTimeInput = document.getElementById('paymentTime');
  
  if (paymentDateInput) {
    const today = new Date();
    paymentDateInput.valueAsDate = today;
  }
  
  if (paymentTimeInput) {
    const now = new Date();
    const hours = String(now.getHours()).padStart(2, '0');
    const minutes = String(now.getMinutes()).padStart(2, '0');
    paymentTimeInput.value = `${hours}:${minutes}`;
  }

  // Setup form submission
  const paymentForm = document.querySelector('#paymentFormContainer form');
  if (paymentForm) {
    paymentForm.addEventListener('submit', handlePaymentSubmit);
  }
});

/**
 * Toggle payment form visibility
 */
function togglePaymentForm() {
  const paymentFormContainer = document.getElementById('paymentFormContainer');
  if (paymentFormContainer) {
    paymentFormContainer.style.display = 
      paymentFormContainer.style.display === 'none' ? 'block' : 'none';
  }
}

/**
 * Handle payment form submission
 */
function handlePaymentSubmit(event) {
  event.preventDefault();
  
  const form = event.target;
  const formData = new FormData(form);
  
  // Create alert container if it doesn't exist
  let alertDiv = document.getElementById('paymentAlert');
  if (!alertDiv) {
    alertDiv = document.createElement('div');
    alertDiv.id = 'paymentAlert';
    alertDiv.style.cssText = `
      margin-bottom: 20px;
      padding: 15px;
      border-radius: 6px;
      display: none;
      font-weight: 600;
    `;
    form.parentElement.insertBefore(alertDiv, form);
  }
  
  // Hide alert initially
  alertDiv.style.display = 'none';
  
  // Get CSRF token
  const csrfToken = document.querySelector('[name=csrfmiddlewaretoken]').value;
  
  // Send form data via fetch
  fetch('/api/payment/record/', {
    method: 'POST',
    headers: {
      'X-CSRFToken': csrfToken,
    },
    body: formData
  })
  .then(response => response.json())
  .then(data => {
    if (data.success) {
      showAlert(alertDiv, data.message, 'success');
      form.reset();
      
      // Reset date and time
      const now = new Date();
      document.getElementById('paymentDate').valueAsDate = now;
      const hours = String(now.getHours()).padStart(2, '0');
      const minutes = String(now.getMinutes()).padStart(2, '0');
      document.getElementById('paymentTime').value = `${hours}:${minutes}`;
      
      // Reload page after 1.5 seconds
      setTimeout(() => {
        window.location.reload();
      }, 1500);
    } else {
      showAlert(alertDiv, data.message || 'An error occurred', 'error');
    }
  })
  .catch(error => {
    console.error('Error:', error);
    showAlert(alertDiv, 'Failed to record payment. Please try again.', 'error');
  });
  
  return false;
}

/**
 * Display alert message
 */
function showAlert(alertDiv, message, type) {
  alertDiv.style.display = 'block';
  alertDiv.textContent = message;
  alertDiv.style.backgroundColor = type === 'success' ? '#d4edda' : '#f8d7da';
  alertDiv.style.color = type === 'success' ? '#155724' : '#721c24';
  alertDiv.style.borderLeft = `4px solid ${type === 'success' ? '#28a745' : '#dc3545'}`;
}
