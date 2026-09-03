import { Route, Routes } from "react-router-dom";

import AppShell from "./components/AppShell";
import About from "./pages/About";
import ApiDocs from "./pages/ApiDocs";
import Chat from "./pages/Chat";
import Conversations from "./pages/Conversations";
import Datasets from "./pages/Datasets";
import Documents from "./pages/Documents";
import KnowledgeSpaces from "./pages/KnowledgeSpaces";
import Models from "./pages/Models";
import NotFound from "./pages/NotFound";
import Settings from "./pages/Settings";
import Training from "./pages/Training";

export default function App() {
  return (
    <Routes>
      <Route element={<AppShell />}>
        <Route index element={<Chat />} />
        <Route path="chat/:conversationId" element={<Chat />} />
        <Route path="conversations" element={<Conversations />} />
        <Route path="knowledge-spaces" element={<KnowledgeSpaces />} />
        <Route path="documents" element={<Documents />} />
        <Route path="training" element={<Training />} />
        <Route path="datasets" element={<Datasets />} />
        <Route path="models" element={<Models />} />
        <Route path="settings" element={<Settings />} />
        <Route path="api-docs" element={<ApiDocs />} />
        <Route path="about" element={<About />} />
        <Route path="*" element={<NotFound />} />
      </Route>
    </Routes>
  );
}
