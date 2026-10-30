import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { createBrowserRouter, RouterProvider } from "react-router-dom";
import "./index.css";
import Shell from "./components/Shell";
import Home from "./pages/Home";
import Inventory from "./pages/Inventory";
import NewWalkthrough from "./pages/NewWalkthrough";
import ListingConsole from "./pages/ListingConsole";
import PublishedPage from "./pages/PublishedPage";
import LiveInIt from "./pages/LiveInIt";

const router = createBrowserRouter([
  { index: true, element: <Home /> },
  {
    element: <Shell />,
    children: [
      { path: "inventory", element: <Inventory /> },
      { path: "new", element: <NewWalkthrough /> },
      { path: "listings/:id", element: <ListingConsole /> },
    ],
  },
  { path: "p/:id", element: <PublishedPage /> },
  { path: "p/:id/live", element: <LiveInIt /> },
  // Three.js only loads on this page.
  {
    path: "prototype-testing",
    hydrateFallbackElement: <div className="fixed inset-0 bg-night" />,
    lazy: () => import("./pages/PrototypeTesting").then((m) => ({ Component: m.default })),
  },
  // Three.js only loads on this page too: static photo + real 3D furniture.
  {
    path: "prototype-static",
    hydrateFallbackElement: <div className="fixed inset-0 bg-night" />,
    lazy: () => import("./pages/PrototypeStatic").then((m) => ({ Component: m.default })),
  },
]);

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <RouterProvider router={router} />
  </StrictMode>,
);
