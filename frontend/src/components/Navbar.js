import React from "react";
import { AppBar, Toolbar, Typography, Button } from "@mui/material";
import { Link } from "react-router-dom";

const Navbar = () => {
  return (
    <AppBar position="static">
      <Toolbar>
        <Typography variant="h6" sx={{ flexGrow: 1 }}>
          Inventar & Assistenten
        </Typography>
        <Button color="inherit" component={Link} to="/">
          Inventar
        </Button>
        <Button color="inherit" component={Link} to="/add">
          Artikel hinzufügen
        </Button>
        <Button color="inherit" component={Link} to="/assistant">
          Recipes
        </Button>
        <Button color="inherit" component={Link} to="/chat">
          Chat
        </Button>
      </Toolbar>
    </AppBar>
  );
};

export default Navbar;
