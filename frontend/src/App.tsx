import { useAuth } from "@/auth/AuthContext";
import { Chat } from "@/components/Chat";
import { Login } from "@/components/Login";

export default function App() {
  const { isAuthenticated } = useAuth();
  return isAuthenticated ? <Chat /> : <Login />;
}
