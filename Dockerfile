FROM oven/bun:1

WORKDIR /app

COPY package.json bun.lock ./
COPY server/package.json server/bun.lock ./server/
COPY client/package.json client/bun.lock ./client/

RUN bun install && bun install --cwd server && bun install --cwd client

COPY server ./server
COPY client ./client

RUN bun run --cwd client build

ENV NODE_ENV=production
EXPOSE 3001

CMD ["bun", "run", "--cwd", "server", "start"]
