import React, { useEffect, useState } from 'react';

const InventoryManager = () => {
  const [inventory, setInventory] = useState([]);

  const fetchInventory = () => {
    fetch('http://localhost:5000/inventory')
      .then((response) => response.json())
      .then((data) => setInventory(data))
      .catch((error) => console.error('Fehler beim Abrufen der Daten:', error));
  };

  useEffect(() => {
    fetchInventory();
  }, []);

  return (
    <div>
      <h1>Inventarverwaltung</h1>
      <table>
        <thead>
          <tr>
            <th>ID</th>
            <th>Name</th>
            <th>Barcode</th>
            <th>Menge</th>
            <th>Kategorie</th>
            <th>Ablaufdatum</th>
            <th>Hinzugefügt am</th>
            <th>Lagerort</th>
          </tr>
        </thead>
        <tbody>
          {inventory.map((item) => (
            <tr key={item.id}>
              <td>{item.id}</td>
              <td>{item.name || 'Unbekannt'}</td>
              <td>{item.barcode}</td>
              <td>{item.quantity}</td>
              <td>{item.category}</td>
              <td>{item.expiration_date || '-'}</td>
              <td>{item.added_date}</td>
              <td>{item.storage_location || 'Unbekannt'}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
};

export default InventoryManager;
