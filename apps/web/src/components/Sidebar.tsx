import type React from "react";
import { Activity, Bot, Building2, CalendarClock, Dumbbell, LineChart, LogOut, UserRound } from "lucide-react";
import type { AuthUser, View } from "../types";

export function Sidebar({
  user,
  activeView,
  setActiveView,
  onLogout,
}: {
  user: AuthUser;
  activeView: View;
  setActiveView: (view: View) => void;
  onLogout: () => void;
}) {
  const items: Array<{ view: View; label: string; icon: React.ReactNode; managerOnly?: boolean; memberOnly?: boolean }> = [
    { view: "overview", label: "User app", icon: <LineChart size={18} />, memberOnly: true },
    { view: "planner", label: "Planner", icon: <CalendarClock size={18} />, memberOnly: true },
    { view: "workouts", label: "Smart notes", icon: <Dumbbell size={18} />, memberOnly: true },
    { view: "coach", label: "AI Coach", icon: <Bot size={18} />, memberOnly: true },
    { view: "profile", label: "Profile", icon: <UserRound size={18} />, memberOnly: true },
    { view: "manager", label: "Manager console", icon: <Building2 size={18} />, managerOnly: true },
    { view: "research", label: "Research", icon: <Activity size={18} />, managerOnly: true },
  ];
  const visibleItems = items.filter((item) => {
    if (user.role === "manager") {
      return item.managerOnly || item.view === "research";
    }
    return !item.managerOnly && !item.memberOnly ? false : item.memberOnly === true;
  });

  return (
    <aside className="sidebar">
      <div className="brand">
        <div className="brand-mark">GF</div>
        <div>
          <h1>GymFlow AI</h1>
          <p>{user.role === "manager" ? "Manager workspace" : "Training workspace"}</p>
        </div>
      </div>
      <nav className="nav">
        {visibleItems.map((item) => (
            <button
              className={activeView === item.view ? "active" : ""}
              key={item.view}
              onClick={() => setActiveView(item.view)}
            >
              {item.icon}
              {item.label}
            </button>
          ))}
      </nav>
      <div className="sidebar-user">
        <span>{user.display_name}</span>
        <button onClick={onLogout}><LogOut size={16} /> Logout</button>
      </div>
    </aside>
  );
}
