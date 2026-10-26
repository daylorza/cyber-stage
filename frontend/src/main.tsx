import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { createBrowserRouter, RouterProvider } from "react-router-dom";
import "./index.css";
import Shell from "./components/Shell";
import Inventory from "./pages/Inventory";
import NewWalkthrough from "./pages/NewWalkthrough";
import ListingConsole from "./pages/ListingConsole";
import PublishedPage from "./pages/PublishedPage";

const router = createBrowserRouter([
  {
    element: <Shell />,
    children: [
      { index: true, element: <Inventory /> },
      { path: "new", element: <NewWalkthrough /> },
      { path: "listings/:id", element: <ListingConsole /> },
    ],
  },
  { path: "p/:id", element: <PublishedPage /> },
]);

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <RouterProvider router={router} />
  </StrictMode>,
);
