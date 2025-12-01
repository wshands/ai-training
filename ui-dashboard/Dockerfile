FROM node:20-alpine
WORKDIR /app
COPY package.json next.config.js /app/
COPY src /app/src
RUN npm install
RUN npm run build
EXPOSE 3000
CMD ["npm", "start"]
