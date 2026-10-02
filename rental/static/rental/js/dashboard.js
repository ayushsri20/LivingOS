/**
 * Dashboard Page - Event Handlers
 * Fixes CSP violations by moving all inline event handlers to external file
 */

document.addEventListener('DOMContentLoaded', function() {
  // Setup building tile click handlers
  setupBuildingTiles();
  
  // Setup room mini click handlers
  setupRoomMiniElements();
  
  // Setup button handlers
  setupButtonHandlers();
  
  // Setup modal close handlers
  setupModalHandlers();
  
  // Setup window click handler for modal closing
  setupWindowClickHandler();
});

/**
 * Setup building tile click handlers
 */
function setupBuildingTiles() {
  const buildingTiles = document.querySelectorAll('[data-building-tile]');
  buildingTiles.forEach(tile => {
    tile.addEventListener('click', function(e) {
      e.stopPropagation();
      const buildingName = this.dataset.buildingTile;
      openBuildingModal(buildingName);
    });
  });
}

/**
 * Setup room mini element click handlers
 */
function setupRoomMiniElements() {
  const roomMinis = document.querySelectorAll('[data-room-mini]');
  roomMinis.forEach(room => {
    room.addEventListener('click', function(e) {
      e.stopPropagation();
      const roomId = this.dataset.roomMini;
      loadRoomTenants(roomId, e);
    });
  });
}

/**
 * Setup button handlers
 */
function setupButtonHandlers() {
  // Manage/View Details buttons
  const manageButtons = document.querySelectorAll('[data-action="manage-building"]');
  manageButtons.forEach(btn => {
    btn.addEventListener('click', function(e) {
      e.stopPropagation();
      const buildingName = this.dataset.building;
      openBuildingModal(buildingName);
    });
  });

  // Toggle room status buttons
  const toggleButtons = document.querySelectorAll('[data-action="toggle-room"]');
  toggleButtons.forEach(btn => {
    btn.addEventListener('click', function(e) {
      e.stopPropagation();
      const roomId = this.dataset.roomId;
      const isAvailable = this.dataset.isAvailable === 'true';
      toggleRoomStatus(roomId, isAvailable);
    });
  });

  // Delete room buttons
  const deleteButtons = document.querySelectorAll('[data-action="delete-room"]');
  deleteButtons.forEach(btn => {
    btn.addEventListener('click', function(e) {
      e.stopPropagation();
      const roomId = this.dataset.roomId;
      deleteRoom(roomId);
    });
  });

  // Document upload buttons
  const uploadButtons = document.querySelectorAll('[data-action="upload-document"]');
  uploadButtons.forEach(btn => {
    btn.addEventListener('click', function(e) {
      e.stopPropagation();
      const tenantId = this.dataset.tenantId;
      const tenantName = this.dataset.tenantName;
      openDocumentUploadModal(tenantId, tenantName);
    });
  });
}

/**
 * Setup modal close handlers
 */
function setupModalHandlers() {
  // Building modal close buttons
  const buildingCloseButtons = document.querySelectorAll('[data-modal-close="building"]');
  buildingCloseButtons.forEach(btn => {
    btn.addEventListener('click', closeBuildingModal);
  });

  // Tenant modal close buttons
  const tenantCloseButtons = document.querySelectorAll('[data-modal-close="tenant"]');
  tenantCloseButtons.forEach(btn => {
    btn.addEventListener('click', closeTenantModal);
  });

  // Document upload modal close buttons
  const docCloseButtons = document.querySelectorAll('[data-modal-close="document"]');
  docCloseButtons.forEach(btn => {
    btn.addEventListener('click', closeDocumentUploadModal);
  });
}

/**
 * Setup window click handler
 */
function setupWindowClickHandler() {
  window.addEventListener('click', function(event) {
    const buildingModal = document.getElementById('buildingModal');
    const tenantModal = document.getElementById('tenantModal');
    const docUploadModal = document.getElementById('documentUploadModal');
    
    if (buildingModal && event.target === buildingModal) {
      closeBuildingModal();
    }
    if (tenantModal && event.target === tenantModal) {
      closeTenantModal();
    }
    if (docUploadModal && event.target === docUploadModal) {
      closeDocumentUploadModal();
    }
  });
}

/**
 * These functions should already exist in the dashboard,
 * but we're providing the event delegation layer
 */
function openBuildingModal(buildingName) {
  // Delegate to existing function
  if (typeof window.openBuildingModal === 'function') {
    window.openBuildingModal(buildingName);
  } else {
    console.log('Opening building modal for:', buildingName);
  }
}

function closeBuildingModal() {
  if (typeof window.closeBuildingModal === 'function') {
    window.closeBuildingModal();
  }
}

function closeTenantModal() {
  if (typeof window.closeTenantModal === 'function') {
    window.closeTenantModal();
  }
}

function closeDocumentUploadModal() {
  if (typeof window.closeDocumentUploadModal === 'function') {
    window.closeDocumentUploadModal();
  }
}

function loadRoomTenants(roomId, event) {
  if (typeof window.loadRoomTenants === 'function') {
    window.loadRoomTenants(roomId, event);
  }
}

function toggleRoomStatus(roomId, isAvailable) {
  if (typeof window.toggleRoomStatus === 'function') {
    window.toggleRoomStatus(roomId, isAvailable);
  }
}

function deleteRoom(roomId) {
  if (typeof window.deleteRoom === 'function') {
    window.deleteRoom(roomId);
  }
}

function openDocumentUploadModal(tenantId, tenantName) {
  if (typeof window.openDocumentUploadModal === 'function') {
    window.openDocumentUploadModal(tenantId, tenantName);
  }
}
