import { AppBar, Button, Toolbar, Typography } from "@mui/material";
import { Link } from "react-router-dom";

const Navbar = () => (
  <AppBar position="static">
    <Toolbar>
      <Typography variant="h6" sx={{ flexGrow: 1 }}>
        Inventar & Assistent
      </Typography>
      <Button color="inherit" component={Link} to="/">
        Inventar
      </Button>
      <Button color="inherit" component={Link} to="/scan">
        Scannen
      </Button>
      <Button color="inherit" component={Link} to="/scan-station">
        Scan-Station
      </Button>
      <Button color="inherit" component={Link} to="/recipes">
        Rezepte
      </Button>
      <Button color="inherit" component={Link} to="/chat">
        Chat
      </Button>
    </Toolbar>
  </AppBar>
);

export default Navbar;
