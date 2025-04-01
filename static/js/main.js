// Receipt upload handling
async function uploadReceipt(file) {
    const formData = new FormData();
    formData.append('file', file);

    // Show loading state
    const uploadSection = document.querySelector('.upload-section');
    const originalContent = uploadSection.innerHTML;
    uploadSection.innerHTML = `
        <div class="text-center">
            <div class="spinner-border text-primary mb-3" role="status">
                <span class="visually-hidden">Loading...</span>
            </div>
            <p class="mb-0">Analyzing receipt...</p>
        </div>
    `;

    try {
        console.log('Uploading file:', file.name); // Debug log
        const response = await fetch('/api/analyze-receipt', {
            method: 'POST',
            body: formData,
            // Add these headers to ensure proper file upload
            headers: {
                // Don't set Content-Type here, let the browser set it with the boundary
                'Accept': 'application/json'
            }
        });

        if (!response.ok) {
            const errorData = await response.json();
            throw new Error(errorData.error || `HTTP error! status: ${response.status}`);
        }

        const data = await response.json();
        
        if (data.success) {
            // Display the extracted items
            displayExtractedItems(data.items);
        } else {
            throw new Error(data.error || 'Failed to process receipt');
        }
    } catch (error) {
        console.error('Error:', error);
        alert('Error uploading receipt: ' + error.message);
    } finally {
        // Restore original upload section content
        uploadSection.innerHTML = originalContent;
    }
}

// Display extracted items in a table
function displayExtractedItems(items) {
    const container = document.getElementById('extracted-items') || document.createElement('div');
    container.id = 'extracted-items';
    container.className = 'mt-4';
    
    container.innerHTML = `
        <div class="card">
            <div class="card-header d-flex justify-content-between align-items-center">
                <h5 class="mb-0">Extracted Items</h5>
                <button onclick='addAllToInventory(${JSON.stringify(items).replace(/'/g, "\\'")})'
                        class="btn btn-primary">
                    Add All to Inventory
                </button>
            </div>
            <div class="card-body">
                <div class="table-responsive">
                    <table class="table">
                        <thead>
                            <tr>
                                <th>Item</th>
                                <th>Quantity</th>
                                <th>Unit</th>
                                <th>Price</th>
                                <th>Action</th>
                            </tr>
                        </thead>
                        <tbody>
                            ${items.map(item => `
                                <tr>
                                    <td>${item.name}</td>
                                    <td>${item.quantity}</td>
                                    <td>${item.unit}</td>
                                    <td>$${item.price ? item.price.toFixed(2) : '0.00'}</td>
                                    <td>
                                        <button onclick='addToInventory(${JSON.stringify(item).replace(/'/g, "\\'")})'
                                                class="btn btn-sm btn-primary">
                                            Add to Inventory
                                        </button>
                                    </td>
                                </tr>
                            `).join('')}
                        </tbody>
                    </table>
                </div>
            </div>
        </div>
    `;

    // If the container isn't already in the document, add it
    if (!document.getElementById('extracted-items')) {
        document.querySelector('.container').appendChild(container);
    }
}

// Add all items to inventory
async function addAllToInventory(items) {
    try {
        // Disable the "Add All" button to prevent double-clicks
        const addAllButton = document.querySelector('#extracted-items .card-header button');
        if (addAllButton) {
            addAllButton.disabled = true;
            addAllButton.innerHTML = '<span class="spinner-border spinner-border-sm" role="status" aria-hidden="true"></span> Adding...';
        }

        // Add each item sequentially with visual feedback
        for (const item of items) {
            // Find the row for this item
            const row = document.querySelector(`tr:has(td:contains("${item.name}"))`);
            if (row) {
                // Add visual feedback class
                row.classList.add('item-adding');
                // Wait a brief moment to show the highlight
                await new Promise(resolve => setTimeout(resolve, 100));
            }

            // Add the item
            await addToInventory(item, false);

            if (row) {
                // Show success state briefly
                row.style.backgroundColor = 'rgba(40, 167, 69, 0.1)';
                await new Promise(resolve => setTimeout(resolve, 300));
                row.style.backgroundColor = '';
            }
        }

        // Refresh inventory once at the end
        await loadInventory();

        // Show success message
        alert(`Successfully added ${items.length} items to inventory`);

        // Clear the extracted items section
        const extractedItems = document.getElementById('extracted-items');
        if (extractedItems) {
            extractedItems.remove();
        }
    } catch (error) {
        console.error('Error adding all items:', error);
        alert('Error adding items to inventory');
    } finally {
        // Re-enable the button if it still exists
        const addAllButton = document.querySelector('#extracted-items .card-header button');
        if (addAllButton) {
            addAllButton.disabled = false;
            addAllButton.textContent = 'Add All to Inventory';
        }
    }
}

// Add an item to inventory
async function addToInventory(item, shouldRefresh = true) {
    try {
        const response = await fetch('/add_item', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
            },
            body: JSON.stringify(item)
        });

        if (!response.ok) {
            throw new Error(`HTTP error! status: ${response.status}`);
        }

        const result = await response.json();
        
        // Only refresh the inventory if shouldRefresh is true
        if (shouldRefresh) {
            await loadInventory();
            
            // Remove the individual row from the extracted items table
            const row = document.querySelector(`tr:has(button[onclick*="${item.name}"])`);
            if (row) {
                row.remove();
            }
            
            // If no more items, remove the entire extracted items section
            const tbody = document.querySelector('#extracted-items tbody');
            if (tbody && !tbody.hasChildNodes()) {
                document.getElementById('extracted-items').remove();
            }
        }
    } catch (error) {
        console.error('Error:', error);
        alert('Error adding item to inventory');
        throw error; // Re-throw the error so addAllToInventory can catch it
    }
}

// Set up file input handling
document.addEventListener('DOMContentLoaded', function() {
    const fileInput = document.querySelector('input[type="file"]');
    if (fileInput) {
        fileInput.addEventListener('change', function(e) {
            const file = e.target.files[0];
            if (file) {
                console.log('Selected file:', file.name); // Debug log
                uploadReceipt(file);
            }
        });
    }

    // Add drag and drop support
    const dropZone = document.querySelector('.upload-section') || document.body;
    
    dropZone.addEventListener('dragover', function(e) {
        e.preventDefault();
        e.stopPropagation();
        this.classList.add('dragover');
    });
    
    dropZone.addEventListener('dragleave', function(e) {
        e.preventDefault();
        e.stopPropagation();
        this.classList.remove('dragover');
    });
    
    dropZone.addEventListener('drop', function(e) {
        e.preventDefault();
        e.stopPropagation();
        this.classList.remove('dragover');
        
        const file = e.dataTransfer.files[0];
        if (file) {
            console.log('Dropped file:', file.name); // Debug log
            uploadReceipt(file);
        }
    });
}); 