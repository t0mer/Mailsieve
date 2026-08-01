import { Route, Routes } from "react-router-dom";

import { Layout } from "./components/Layout";
import { Diff } from "./pages/Diff";
import { History } from "./pages/History";
import { Home } from "./pages/Home";
import { Settings } from "./pages/Settings";

export function App() {
  return (
    <Routes>
      <Route element={<Layout />}>
        <Route index element={<Home />} />
        <Route path="history" element={<History />} />
        <Route path="diff/:email" element={<Diff />} />
        <Route path="settings" element={<Settings />} />
        <Route path="*" element={<Home />} />
      </Route>
    </Routes>
  );
}
