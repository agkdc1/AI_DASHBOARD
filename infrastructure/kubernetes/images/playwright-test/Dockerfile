FROM mcr.microsoft.com/playwright:v1.50.1-noble

WORKDIR /tests

# Install dependencies
COPY package.json package-lock.json* ./
RUN npm install

# Copy test files
COPY tests/ ./tests/
COPY playwright.config.ts ./

CMD ["npx", "playwright", "test", "--reporter=html"]
