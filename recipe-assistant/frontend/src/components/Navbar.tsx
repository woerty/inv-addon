import { useState } from "react";
import {
  AppBar,
  Box,
  Drawer,
  IconButton,
  List,
  ListItemButton,
  ListItemIcon,
  ListItemText,
  Toolbar,
  Typography,
} from "@mui/material";
import MenuIcon from "@mui/icons-material/Menu";
import InventoryIcon from "@mui/icons-material/Inventory2";
import QrCodeScannerIcon from "@mui/icons-material/QrCodeScanner";
import CropFreeIcon from "@mui/icons-material/CropFree";
import RestaurantIcon from "@mui/icons-material/Restaurant";
import ChatIcon from "@mui/icons-material/Chat";
import PeopleIcon from "@mui/icons-material/People";
import LocalGroceryStoreIcon from "@mui/icons-material/LocalGroceryStore";
import ShoppingCartIcon from "@mui/icons-material/ShoppingCart";
import LoginIcon from "@mui/icons-material/Login";
import { useNavigate, useLocation } from "react-router-dom";
import { usePicnicStatus } from "../hooks/usePicnic";

const NAV_ITEMS = [
  { path: "/", label: "Inventar", icon: <InventoryIcon /> },
  { path: "/scan", label: "Scannen", icon: <QrCodeScannerIcon /> },
  { path: "/scan-station", label: "Scan-Station", icon: <CropFreeIcon /> },
  { path: "/recipes", label: "Rezepte", icon: <RestaurantIcon /> },
  { path: "/chat", label: "Chat", icon: <ChatIcon /> },
  { path: "/persons", label: "Personen", icon: <PeopleIcon /> },
];

const Navbar = () => {
  const [drawerOpen, setDrawerOpen] = useState(false);
  const navigate = useNavigate();
  const location = useLocation();
  const { status } = usePicnicStatus();

  const navItems = [
    ...NAV_ITEMS,
    ...(status?.enabled
      ? [
          { path: "/picnic-import", label: "Picnic-Import", icon: <LocalGroceryStoreIcon /> },
          { path: "/shopping-list", label: "Einkaufsliste", icon: <ShoppingCartIcon /> },
        ]
      : status?.needs_login
      ? [
          { path: "/picnic-login", label: "Picnic Login", icon: <LoginIcon /> },
        ]
      : []),
  ];

  const handleNav = (path: string) => {
    navigate(path);
    setDrawerOpen(false);
  };

  return (
    <>
      <AppBar position="static">
        <Toolbar>
          <IconButton
            color="inherit"
            edge="start"
            onClick={() => setDrawerOpen(true)}
            sx={{ mr: 2 }}
          >
            <MenuIcon />
          </IconButton>
          <Typography variant="h6" sx={{ flexGrow: 1 }}>
            Inventar & Assistent
          </Typography>
        </Toolbar>
      </AppBar>

      <Drawer
        anchor="left"
        open={drawerOpen}
        onClose={() => setDrawerOpen(false)}
      >
        <Box sx={{ width: 250, pt: 1 }}>
          <List>
            {navItems.map((item) => (
              <ListItemButton
                key={item.path}
                selected={location.pathname === item.path}
                onClick={() => handleNav(item.path)}
              >
                <ListItemIcon>{item.icon}</ListItemIcon>
                <ListItemText primary={item.label} />
              </ListItemButton>
            ))}
          </List>
        </Box>
      </Drawer>
    </>
  );
};

export default Navbar;
