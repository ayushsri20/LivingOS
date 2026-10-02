/**
 * Book Room Page - Event Handlers
 * Fixes CSP violations by moving all inline event handlers to external file
 */

document.addEventListener('DOMContentLoaded', function() {
  // Setup form submission
  const bookingForm = document.querySelector('form[action*="booking"]') || 
                      document.querySelector('form');
  
  if (bookingForm) {
    bookingForm.addEventListener('submit', handleBookingSubmit);
  }

  // Setup room selection change listeners
  const roomSelect = document.querySelector('select[name="room_id"]');
  if (roomSelect) {
    roomSelect.addEventListener('change', updateRoomDetails);
  }

  // Setup cancel button
  const cancelButton = document.querySelector('[data-action="cancel"]');
  if (cancelButton) {
    cancelButton.addEventListener('click', function(e) {
      e.preventDefault();
      window.history.back();
    });
  }
});

/**
 * Update room details when selection changes
 */
function updateRoomDetails(event) {
  const roomId = event.target.value;
  if (!roomId) return;

  fetch(`/api/room/${roomId}/details/`, {
    method: 'GET',
    headers: {
      'Content-Type': 'application/json',
    }
  })
  .then(response => response.json())
  .then(data => {
    if (data.success) {
      // Update room price and details
      const priceElement = document.getElementById('roomPrice');
      if (priceElement) {
        const displayPrice = data.room.agreed_rent && data.room.agreed_rent.length ? data.room.agreed_rent : data.room.price_per_month;
        priceElement.textContent = `₹${displayPrice}`;
      }
      
      const descElement = document.getElementById('roomDescription');
      if (descElement) {
        descElement.textContent = data.room.description || 'No description available';
      }
    }
  })
  .catch(error => console.error('Error fetching room details:', error));
}

/**
 * Handle booking form submission
 */
function handleBookingSubmit(event) {
  event.preventDefault();
  
  const form = event.target;
  const formData = new FormData(form);
  
  // Get or create alert div
  let alertDiv = document.getElementById('bookingAlert');
  if (!alertDiv) {
    alertDiv = document.createElement('div');
    alertDiv.id = 'bookingAlert';
    alertDiv.style.cssText = `
      margin-bottom: 20px;
      padding: 15px 20px;
      border-radius: 6px;
      font-weight: 600;
      display: none;
      border-left: 4px solid;
    `;
    form.parentElement.insertBefore(alertDiv, form);
  }
  
  alertDiv.style.display = 'none';
  
  // Get CSRF token
  const csrfToken = document.querySelector('[name=csrfmiddlewaretoken]').value;
  
  // Show loading state
  const submitBtn = form.querySelector('button[type="submit"]');
  const originalText = submitBtn.textContent;
  submitBtn.disabled = true;
  submitBtn.textContent = 'Processing...';
  
  // Submit form
  fetch(form.action || '/booking/', {
    method: 'POST',
    headers: {
      'X-CSRFToken': csrfToken,
    },
    body: formData
  })
  .then(response => response.json())
  .then(data => {
    if (data.success) {
      showBookingAlert(alertDiv, data.message, 'success');
      form.reset();
      
      // Redirect to dashboard after 1.5 seconds
      setTimeout(() => {
        window.location.href = '/dashboard/';
      }, 1500);
    } else {
      showBookingAlert(alertDiv, data.message || 'An error occurred', 'error');
      submitBtn.disabled = false;
      submitBtn.textContent = originalText;
    }
  })
  .catch(error => {
    console.error('Error:', error);
    showBookingAlert(alertDiv, 'Failed to complete booking. Please try again.', 'error');
    submitBtn.disabled = false;
    submitBtn.textContent = originalText;
  });
  
  return false;
}

/**
 * Display booking alert
 */
function showBookingAlert(alertDiv, message, type) {
  alertDiv.style.display = 'block';
  alertDiv.textContent = message;
  
  if (type === 'success') {
    alertDiv.style.backgroundColor = '#d4edda';
    alertDiv.style.color = '#155724';
    alertDiv.style.borderLeftColor = '#28a745';
  } else {
    alertDiv.style.backgroundColor = '#f8d7da';
    alertDiv.style.color = '#721c24';
    alertDiv.style.borderLeftColor = '#dc3545';
  }
}
