# Backend - Flask API
FROM python:3.11 AS backend
WORKDIR /app
COPY app/ /app/
RUN pip install --no-cache-dir -r requirements.txt

# Frontend - React App
FROM node:18 AS frontend
WORKDIR /frontend
COPY frontend/ /frontend/
RUN npm install && npm run build

# Final Container
FROM python:3.11
WORKDIR /app

# Kopiere Backend & Frontend
COPY --from=backend /app /app
COPY --from=frontend /frontend/build /app/frontend

# Installiere Flask Dependencies
RUN pip install --no-cache-dir -r /app/requirements.txt

# Exponiere Ports
EXPOSE 5000

# Starte Flask & Serve React
CMD ["sh", "/app/run.sh"]
