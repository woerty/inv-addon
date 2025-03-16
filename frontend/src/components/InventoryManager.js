import React, { useEffect, useState, useCallback } from 'react';
import {
  Table,
  TableBody,
  TableCell,
  TableContainer,
  TableHead,
  TableRow,
  Paper,
  TextField,
  TableSortLabel,
  Typography,
  Button,
} from '@mui/material';

const InventoryManager = ({ showNotification }) => {
  const [inventory, setInventory] = useState([]);
  const [searchQuery, setSearchQuery] = useState('');
  const [sortConfig, setSortConfig] = useState({ key: 'name', direction: 'asc' });
  const [editFields, setEditFields] = useState({});

  const fetchInventory = () => {
    fetch('http://localhost:5000/inventory')
      .then((response) => response.json())
      .then((data) => setInventory(data))
      .catch(() => showNotification('Fehler beim Abrufen der Daten', 'error'));
  };

  useEffect(() => {
    fetchInventory();
  }, []);

  const handleSearchChange = (event) => {
    setSearchQuery(event.target.value);
  };

  const handleSort = (key) => {
    setSortConfig((prev) => {
      const isAsc = prev.key === key && prev.direction === 'asc';
      return { key, direction: isAsc ? 'desc' : 'asc' };
    });
  };

  const handleFieldChange = (id, field, value) => {
    setEditFields({ ...editFields, [id]: { ...editFields[id], [field]: value } });
  };

  const handleUpdate = (id, barcode) => {
    const updates = editFields[id] || {};
    const newQuantity = parseInt(updates.quantity, 10);

    if (isNaN(newQuantity) || newQuantity < 0) return;

    if (newQuantity === 0) {
      if (window.confirm('Artikel wirklich löschen?')) {
        fetch(`http://localhost:5000/inventory/${barcode}`, {
          method: 'DELETE',
        })
          .then((response) => response.json())
          .then((data) => {
            showNotification(data.message, 'success');
            fetchInventory();
          })
          .catch(() => showNotification('Fehler beim Löschen des Artikels', 'error'));
      }
    } else {
      fetch(`http://localhost:5000/inventory/${barcode}`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          quantity: newQuantity,
          storage_location: updates.storage_location || '',
        }),
      })
        .then((response) => response.json())
        .then((data) => {
          showNotification(data.message, 'success');
          fetchInventory();
        })
        .catch(() => showNotification('Fehler beim Ändern der Menge oder des Lagerortes', 'error'));
    }
  };

  const sortedInventory = [...inventory].sort((a, b) => {
    if (a[sortConfig.key] < b[sortConfig.key]) {
      return sortConfig.direction === 'asc' ? -1 : 1;
    }
    if (a[sortConfig.key] > b[sortConfig.key]) {
      return sortConfig.direction === 'asc' ? 1 : -1;
    }
    return 0;
  });

  const filteredInventory = sortedInventory.filter((item) =>
    item.name?.toLowerCase().includes(searchQuery.toLowerCase()) ||
    item.category?.toLowerCase().includes(searchQuery.toLowerCase())
  );

  return (
    <Paper sx={{ padding: 2 }}>
      <Typography variant="h4" gutterBottom>
        Inventarverwaltung
      </Typography>
      <TextField
        label="Suche nach Name oder Kategorie"
        variant="outlined"
        fullWidth
        margin="normal"
        value={searchQuery}
        onChange={handleSearchChange}
      />
      <TableContainer>
        <Table>
          <TableHead>
            <TableRow>
              {['id', 'name', 'barcode', 'quantity', 'category', 'expiration_date', 'added_date', 'storage_location', 'Aktion'].map((key) => (
                <TableCell key={key}>
                  <TableSortLabel
                    active={sortConfig.key === key}
                    direction={sortConfig.key === key ? sortConfig.direction : 'asc'}
                    onClick={() => handleSort(key)}
                  >
                    {key.replace('_', ' ').toUpperCase()}
                  </TableSortLabel>
                </TableCell>
              ))}
            </TableRow>
          </TableHead>
          <TableBody>
            {filteredInventory.map((item) => (
              <TableRow key={item.id}>
                <TableCell>{item.id}</TableCell>
                <TableCell>{item.name || 'Unbekannt'}</TableCell>
                <TableCell>{item.barcode}</TableCell>
                <TableCell>
                  <TextField
                    type="number"
                    size="small"
                    value={editFields[item.id]?.quantity || item.quantity}
                    onChange={(e) => handleFieldChange(item.id, 'quantity', e.target.value)}
                    style={{ width: '70px' }}
                  />
                </TableCell>
                <TableCell>{item.category}</TableCell>
                <TableCell>{item.expiration_date || '-'}</TableCell>
                <TableCell>{item.added_date}</TableCell>
                <TableCell>
                  <TextField
                    size="small"
                    value={editFields[item.id]?.storage_location || item.storage_location}
                    onChange={(e) => handleFieldChange(item.id, 'storage_location', e.target.value)}
                    style={{ width: '120px' }}
                  />
                </TableCell>
                <TableCell>
                  <Button
                    variant="contained"
                    color="primary"
                    size="small"
                    onClick={() => handleUpdate(item.id, item.barcode)}
                  >
                    Ändern
                  </Button>
                </TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </TableContainer>
    </Paper>
  );
};

export default InventoryManager;
