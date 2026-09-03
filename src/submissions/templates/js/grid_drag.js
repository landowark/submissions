
const gridContainer = document.getElementById("plate-container");
let draggedItem = null;
let selectedIndices = new Set();
let lastClickedIndex = null;
const plateRows = parseInt(gridContainer.getAttribute("data-rows")) || 8;
const plateColumns = parseInt(gridContainer.getAttribute("data-columns")) || 12;

// Utility functions
function getWellIndex(well) {
  return [...gridContainer.children].indexOf(well);
}

function getRowColumn(index) {
  // Grid uses column-major flow (flows down first, then right)
  const row = index % plateRows;
  const col = Math.floor(index / plateRows);
  return { row, col };
}

function getIndexFromRowCol(row, col) {
  return col * plateRows + row;
}

function highlightSelected() {
  const wells = gridContainer.querySelectorAll('.well');
  wells.forEach((well, index) => {
    if (selectedIndices.has(index)) {
      well.classList.add('selected');
    } else {
      well.classList.remove('selected');
    }
  });
}

function isFullRowSelected(rowIndex) {
  // In column-major layout, a full row spans all columns
  for (let col = 0; col < plateColumns; col++) {
    const index = col * plateRows + rowIndex;
    if (!selectedIndices.has(index)) return false;
  }
  return true;
}

function isFullColumnSelected(colIndex) {
  // In column-major layout, a full column is a contiguous set
  const start = colIndex * plateRows;
  const end = start + plateRows;
  for (let i = start; i < end; i++) {
    if (!selectedIndices.has(i)) return false;
  }
  return true;
}

function getSelectedRows() {
  const rows = new Set();
  selectedIndices.forEach(index => {
    rows.add(index % plateRows);
  });
  return Array.from(rows).sort((a, b) => a - b);
}

function getSelectedColumns() {
  const cols = new Set();
  selectedIndices.forEach(index => {
    cols.add(Math.floor(index / plateRows));
  });
  return Array.from(cols).sort((a, b) => a - b);
}

function moveRowsOrColumns(draggedIndex, targetIndex) {
  const draggedRow = draggedIndex % plateRows;
  const draggedCol = Math.floor(draggedIndex / plateRows);
  const targetRow = targetIndex % plateRows;
  const targetCol = Math.floor(targetIndex / plateRows);

  const selectedRows = getSelectedRows();
  const selectedCols = getSelectedColumns();
  
  // Check if full rows are selected
  let fullRowsSelected = selectedRows.every(row => isFullRowSelected(row));
  // Check if full columns are selected
  let fullColsSelected = selectedCols.every(col => isFullColumnSelected(col));

  if (fullRowsSelected && selectedRows.length > 0) {
    // Move entire rows
    moveRows(selectedRows, targetRow);
  } else if (fullColsSelected && selectedCols.length > 0) {
    // Move entire columns
    moveColumns(selectedCols, targetCol);
  } else {
    // Move individual wells
    moveWells(draggedIndex, targetIndex);
  }
}

function moveRows(rowIndices, targetRow) {
  const wells = [...gridContainer.children];
  const rowsToMove = [];
  
  // Collect all wells in selected rows in order
  for (let col = 0; col < plateColumns; col++) {
    rowIndices.forEach(rowIdx => {
      const wellIndex = col * plateRows + rowIdx;
      if (wellIndex < wells.length) {
        rowsToMove.push(wells[wellIndex]);
      }
    });
  }

  const firstSelectedRow = Math.min(...rowIndices);
  const lastSelectedRow = Math.max(...rowIndices);

  // Don't move if target is within selection
  if (targetRow >= firstSelectedRow && targetRow <= lastSelectedRow) return;

  // Find insertion point at target row
  let insertionPoint;
  if (targetRow < firstSelectedRow) {
    insertionPoint = wells[targetRow];
  } else {
    insertionPoint = wells[targetRow];
  }

  // Move wells to new position
  rowsToMove.forEach(well => {
    if (insertionPoint) {
      gridContainer.insertBefore(well, insertionPoint);
    } else {
      gridContainer.appendChild(well);
    }
  });
}

function moveColumns(colIndices, targetCol) {
  const wells = [...gridContainer.children];
  const colsToMove = [];
  
  // Collect all wells in selected columns in order
  colIndices.forEach(colIdx => {
    const start = colIdx * plateRows;
    const end = start + plateRows;
    for (let i = start; i < end; i++) {
      if (i < wells.length) {
        colsToMove.push(wells[i]);
      }
    }
  });

  const firstSelectedCol = Math.min(...colIndices);
  const lastSelectedCol = Math.max(...colIndices);

  // Don't move if target is within selection
  if (targetCol >= firstSelectedCol && targetCol <= lastSelectedCol) return;

  // Find insertion point at target column
  const insertionIndex = targetCol * plateRows;
  const insertionPoint = wells[insertionIndex] || null;

  // Move wells to new position
  colsToMove.forEach(well => {
    if (insertionPoint) {
      gridContainer.insertBefore(well, insertionPoint);
    } else {
      gridContainer.appendChild(well);
    }
  });
}

function moveWells(draggedIndex, targetIndex) {
  const wells = [...gridContainer.children];
  const draggedItem = wells[draggedIndex];
  const targetItem = wells[targetIndex];

  if (draggedIndex < targetIndex) {
    gridContainer.insertBefore(draggedItem, targetItem.nextSibling);
  } else {
    gridContainer.insertBefore(draggedItem, targetItem);
  }
}

// Click event for selection
gridContainer.addEventListener("click", (e) => {
  const well = e.target.closest('.well');
  if (!well) return;

  const index = getWellIndex(well);

  if (e.ctrlKey) {
    // Ctrl+Click: toggle selection
    if (selectedIndices.has(index)) {
      selectedIndices.delete(index);
    } else {
      selectedIndices.add(index);
    }
    lastClickedIndex = index;
  } else if (e.shiftKey && lastClickedIndex !== null) {
    // Shift+Click: extend selection
    const start = Math.min(lastClickedIndex, index);
    const end = Math.max(lastClickedIndex, index);
    for (let i = start; i <= end; i++) {
      selectedIndices.add(i);
    }
  } else {
    // Regular click: clear selection (will be handled by drag if this well is draggable)
    selectedIndices.clear();
    lastClickedIndex = index;
  }

  highlightSelected();
  e.stopPropagation();
});

// Handle Drag start
gridContainer.addEventListener("dragstart", (e) => {
  draggedItem = e.target.closest('.well');
  if (!draggedItem) return;

  const draggedIndex = getWellIndex(draggedItem);

  // If dragging a non-selected item, clear selection and select only this one
  if (!selectedIndices.has(draggedIndex)) {
    selectedIndices.clear();
    selectedIndices.add(draggedIndex);
    highlightSelected();
  }

  draggedItem.style.opacity = "0.5";
});

// Handle Drag End
gridContainer.addEventListener("dragend", (e) => {
  if (draggedItem) {
    draggedItem.style.opacity = "1";
    draggedItem = null;
  }
});

// Handle dragging over grid items
gridContainer.addEventListener("dragover", (e) => {
  e.preventDefault();
});

// Handle Drop
gridContainer.addEventListener("drop", (e) => {
  e.preventDefault();
  if (!draggedItem) return;

  const targetItem = e.target.closest('.well');
  if (!targetItem || targetItem === draggedItem) return;

  const draggedIndex = getWellIndex(draggedItem);
  const targetIndex = getWellIndex(targetItem);

  // Ensure dragged item is in selection
  if (!selectedIndices.has(draggedIndex)) {
    selectedIndices.clear();
    selectedIndices.add(draggedIndex);
  }

  moveRowsOrColumns(draggedIndex, targetIndex);
  
  output = [];
  fullGrid = [...gridContainer.children];
  fullGrid.forEach(function(item, index) {
    output.push({sample_id: item.id, index: index + 1, class: item.className});
  });

  rearrange_plate();
  selectedIndices.clear();
  highlightSelected();
});