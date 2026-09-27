"use client";

import { createContext, useCallback, useContext, useState, type ReactNode } from "react";
import { api, type User } from "@/lib/api";

const Ctx = createContext<{ user: User; setUser: (u: User) => void; refresh: () => Promise<void> } | null>(null);

/** Server-fetched /me, refreshable from the client (e.g. after credits change). */
export function UserProvider({ initial, children }: { initial: User; children: ReactNode }) {
  const [state, setState] = useState({ initial, user: initial });
  if (state.initial !== initial) setState({ initial, user: initial }); // server re-render wins
  const setUser = useCallback((user: User) => setState((s) => ({ ...s, user })), []);
  const refresh = useCallback(async () => {
    try {
      setUser(await api<User>("/me"));
    } catch {
      // keep the last known user; the next navigation re-checks the session
    }
  }, [setUser]);
  return <Ctx.Provider value={{ user: state.user, setUser, refresh }}>{children}</Ctx.Provider>;
}

export function useUser() {
  const c = useContext(Ctx);
  if (!c) throw new Error("useUser must be used inside <UserProvider>");
  return c;
}

