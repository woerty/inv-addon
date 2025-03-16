import React, { useEffect, useState } from 'react';

const DeleteItem = () => {
  const [inventory, setInventory] = useState([]);

  const fetchInventory = () => {
    fetch('http://localhost:5000/inventory')
      .then((response) => response.json())
      .then((data) => setInventory(data))
      .catch((error) => console.error('Fehler beim Abrufen:', error));
  };

  useEffect(() => {
    fetchInventory();
  }, []);

  const handleDelete = (barcode) => {
    if (window.confirm('Artikel wirklich löschen?')) {
      fetch(`http://localhost:5000/inventory/${barcode}`, {
        method: 'DELETE',
      })
        .then((response) => response.json())
        .then((data) => {
          alert(data.message);
          fetchInventory();
        })
        .catch((error) => {
          console.error('Fehler beim Löschen:', error);
          alert('Fehler beim Löschen des Artikels');
        });
    }
  };

  useEffect(() => {
    fetchInventory();
  }, []);

  return (
    <div>
      <h2>Artikel entfernen</h2>
      <table>
        <thead>
          <tr>
            <th>Name</th>
            <th>Barcode</th>
            <th>Menge</th>
            <th>Aktion</th>
          </tr>
        </thead>
        <tbody>
          {inventory.map((item) => (
            <tr key={item.id}>
              <td>{item.name || 'Unbekannt'}</td>
              <td>{item.barcode}</td>
              <td>{item.quantity}</td>
              <td>
                <button onClick={() => handleDelete(item.barcode)}>Löschen</button>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
};

export default DeleteItem;
