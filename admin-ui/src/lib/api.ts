import axios from "axios";

const api = axios.create({
  baseURL: "/api/admin",
  withCredentials: true,
  headers: { "Content-Type": "application/json" },
});

// NO redirigimos aquí — ProtectedRoute maneja la redirección al login
// El interceptor solo rechaza la promesa para que los componentes sepan del error
api.interceptors.response.use(
  (r) => r,
  (err) => Promise.reject(err)
);

export default api;
