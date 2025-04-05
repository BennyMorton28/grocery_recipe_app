// Receipt upload handling
async function uploadReceipt(file) {
    console.log('Starting receipt upload process...');
    console.log('File details:', {
        name: file.name,
        type: file.type,
        size: file.size
    });

    const formData = new FormData();
    formData.append('receipt', file);

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
        console.log('Sending request to /api/upload_receipt...');
        const response = await fetch('/api/upload_receipt', {
            method: 'POST',
            body: formData
        });

        console.log('Response received:', {
            status: response.status,
            statusText: response.statusText,
            headers: Object.fromEntries(response.headers)
        });

        if (!response.ok) {
            const errorData = await response.json();
            console.error('Error response:', errorData);
            throw new Error(errorData.error || `HTTP error! status: ${response.status}`);
        }

        const data = await response.json();
        console.log('Response data:', data);
        
        if (data.success) {
            console.log('Successfully processed receipt. Items:', data.items);
            // Display the extracted items
            displayExtractedItems(data.items);
        } else {
            console.error('Failed to process receipt:', data.error);
            throw new Error(data.error || 'Failed to process receipt');
        }
    } catch (error) {
        console.error('Error in uploadReceipt:', error);
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
        console.log('Attempting to add item:', item); // Debug log
        const response = await fetch('/api/add_item', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
            },
            body: JSON.stringify(item)  // Send the item directly, not wrapped in an items array
        });

        console.log('Response status:', response.status); // Debug log
        console.log('Response headers:', Object.fromEntries(response.headers)); // Debug log

        if (!response.ok) {
            const errorText = await response.text();
            console.error('Error response:', errorText); // Debug log
            throw new Error(`HTTP error! status: ${response.status}, message: ${errorText}`);
        }

        const result = await response.json();
        console.log('Success response:', result); // Debug log
        
        // Only refresh the inventory if shouldRefresh is true
        if (shouldRefresh) {
            console.log('Refreshing inventory...'); // Debug log
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
        console.error('Detailed error:', error); // Debug log
        alert('Error adding item to inventory: ' + error.message);
        throw error; // Re-throw the error so addAllToInventory can catch it
    }
}

// Function to handle adding item from the modal
async function addItemToInventory() {
    const name = document.getElementById('itemName').value;
    const quantity = parseFloat(document.getElementById('itemQuantity').value);
    const unit = document.getElementById('itemUnit').value;
    const price = parseFloat(document.getElementById('itemPrice').value);

    console.log('Form values:', { name, quantity, unit, price }); // Debug log

    if (!name || !quantity || !unit || !price) {
        console.log('Missing required fields:', { name, quantity, unit, price }); // Debug log
        alert('Please fill in all fields');
        return;
    }

    const item = {
        name,
        quantity,
        unit,
        price
    };

    try {
        console.log('Submitting item:', item); // Debug log
        const response = await fetch('/api/add_item', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
            },
            body: JSON.stringify(item)  // Send the item directly, not wrapped in an items array
        });

        console.log('Response status:', response.status); // Debug log
        
        const data = await response.json();
        console.log('Response data:', data); // Debug log
        
        if (data.success) {
            // Close the modal
            const modal = bootstrap.Modal.getInstance(document.getElementById('addItemModal'));
            if (modal) {
                modal.hide();
                console.log('Modal closed'); // Debug log
            } else {
                console.error('Modal instance not found'); // Debug log
            }
            
            // Clear the form
            document.getElementById('addItemForm').reset();
            console.log('Form reset'); // Debug log
            
            // Refresh the inventory display
            await loadInventory();
            console.log('Inventory refreshed'); // Debug log
        } else {
            alert(data.error || 'Failed to add item');
        }
    } catch (error) {
        console.error('Error in addItemToInventory:', error); // Debug log
        alert('Error adding item: ' + error.message);
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

// Load inventory items
async function loadInventory() {
    console.log('Loading inventory...'); // Debug log
    try {
        const response = await fetch('/api/inventory');
        console.log('Inventory response status:', response.status); // Debug log

        if (!response.ok) {
            throw new Error(`HTTP error! status: ${response.status}`);
        }

        const data = await response.json();
        console.log('Inventory data:', data); // Debug log
        
        const inventoryList = document.getElementById('inventory-list');
        if (!inventoryList) {
            console.error('Inventory list element not found');
            return;
        }

        if (data.items && data.items.length > 0) {
            inventoryList.innerHTML = `
                <table class="table table-hover">
                    <thead>
                        <tr>
                            <th>Item</th>
                            <th class="text-center">Qty</th>
                            <th class="text-center">Unit</th>
                            <th class="text-end">Price</th>
                            <th class="text-end">Action</th>
                        </tr>
                    </thead>
                    <tbody>
                        ${data.items.map(item => `
                            <tr>
                                <td class="text-nowrap">${item.name}</td>
                                <td class="text-center">${item.quantity}</td>
                                <td class="text-center">${item.unit}</td>
                                <td class="text-end">$${item.price.toFixed(2)}</td>
                                <td class="text-end">
                                    <button onclick="deleteItem('${item._id}')" class="btn btn-danger btn-sm">
                                        <i class="fas fa-trash"></i>
                                    </button>
                                </td>
                            </tr>
                        `).join('')}
                    </tbody>
                </table>
            `;
        } else {
            inventoryList.innerHTML = `
                <div class="text-center text-muted p-4">
                    <i class="fas fa-box-open fa-3x mb-3"></i>
                    <p class="mb-0">No items in inventory</p>
                </div>
            `;
        }
    } catch (error) {
        console.error('Error loading inventory:', error);
        const inventoryList = document.getElementById('inventory-list');
        if (inventoryList) {
            inventoryList.innerHTML = `
                <div class="text-center text-danger p-4">
                    <i class="fas fa-exclamation-circle fa-3x mb-3"></i>
                    <p class="mb-0">Error loading inventory</p>
                </div>
            `;
        }
    }
} 