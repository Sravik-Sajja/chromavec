FROM node:20-bookworm-slim

WORKDIR /app

COPY package*.json ./
RUN npm install

COPY . .

EXPOSE 5173

# --host exposes the dev server outside the container; without it Vite
# only binds to localhost inside the container and you can't reach it.
CMD ["npm", "run", "dev", "--", "--host", "0.0.0.0"]