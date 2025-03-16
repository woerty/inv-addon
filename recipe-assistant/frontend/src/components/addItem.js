import React, { useState } from 'react';

const AddItem = () => {
  const [formData, setFormData] = useState({
    name: '',
    barcode: '',
    quantity: 1,
    expiration_date: '',
    category: ''
  });

  const handleChange = (e) => {
    const { name, value } = e.target;
    setFormData({ ...formData, [name]: value });
  };

  const handleSubmit = (e) => {
    e.preventDefault();

    fetch('http://localhost:5000/inventory', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json'
      },
      body: JSON.stringify(formData)
    })
    .then((response) => response.json())
    .then((data) => {
      alert(data.message);
      setFormData({
        name: '',
        barcode: '',
        quantity: 1,
        expiration_date: '',
        category: ''
      });
    })
    .catch((error) => {
      console.error('Fehler beim Hinzufügen:', error);
      alert('Fehler beim Hinzufügen des Artikels');
    });
  };

  return (
    <div>
      <h2>Neuen Artikel hinzufügen</h2>
      <form onSubmit={handleSubmit}>
        <input type="text" name="name" placeholder="Artikelname" value={formData.name} onChange={handleChange} required />
        <input type="text" name="barcode" placeholder="Barcode" value={formData.barcode} onChange={handleChange} required />
        <input type="number" name="quantity" placeholder="Menge" value={formData.quantity} onChange={handleChange} required min="1" />
        <input type="date" name="expiration_date" placeholder="Ablaufdatum" value={formData.expiration_date} onChange={handleChange} />
        <input type="text" name="category" placeholder="Kategorie" value={formData.category} onChange={handleChange} required />
        <button type="submit">Hinzufügen</button>
      </form>
    </div>
  );
};

export default AddItem;
