/**
 * Manage Electricity Bills Page - Event Handlers
 * Fixes CSP violations by moving all inline event handlers to external file
 */

document.addEventListener('DOMContentLoaded', function() {
  // Setup Add Bill button
  const addBillBtn = document.getElementById('addBillBtn');
  if (addBillBtn) {
    addBillBtn.addEventListener('click', function() {
      showAlert('Add bill functionality coming soon', 'info');
    });
  }

  // Setup any other button handlers if needed
  setupBillCardButtons();
});

/**
 * Setup bill card action buttons
 */
function setupBillCardButtons() {
  // Record payment buttons
  const recordButtons = document.querySelectorAll('[data-action="record-bill-payment"]');
  recordButtons.forEach(btn => {
    btn.addEventListener('click', function(e) {
      e.preventDefault();
      const billId = this.dataset.billId;
      recordBillPayment(billId);
    });
  });

  // History buttons
  const historyButtons = document.querySelectorAll('[data-action="bill-history"]');
  historyButtons.forEach(btn => {
    btn.addEventListener('click', function(e) {
      e.preventDefault();
      const roomId = this.dataset.roomId;
      showBillHistory(roomId);
    });
  });
}

/**
 * Display alert message
 */
function showAlert(message, type = 'info') {
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
  
  const colors = {
    success: { bg: '#d4edda', color: '#155724', border: '#28a745' },
    error: { bg: '#f8d7da', color: '#721c24', border: '#dc3545' },
    info: { bg: '#d1ecf1', color: '#0c5460', border: '#17a2b8' }
  };
  
  const colorScheme = colors[type] || colors.info;
  alertDiv.style.backgroundColor = colorScheme.bg;
  alertDiv.style.color = colorScheme.color;
  alertDiv.style.borderLeftColor = colorScheme.border;
  
  setTimeout(() => {
    alertDiv.style.display = 'none';
  }, 4000);
}

/**
 * Record bill payment
 */
function recordBillPayment(billId) {
  console.log('Recording payment for bill:', billId);
  showAlert('Bill payment recording coming soon', 'info');
}

/**
 * Show bill history
 */
function showBillHistory(roomId) {
  console.log('Showing bill history for room:', roomId);
  showAlert('Bill history coming soon', 'info');
}
