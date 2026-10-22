import { client } from "./client";

export const authenticate = (role, identity, password) =>
  client.post("/auth/login", { role, identity, password }).then(response => response.data);

export const changeAdminPassword = (newPassword, setupToken) =>
  client.post(
    "/auth/admin-password",
    { new_password: newPassword },
    { headers: { "X-Admin-Setup-Token": setupToken } },
  ).then(response => response.data);
