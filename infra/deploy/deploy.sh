#!/usr/bin/env sh
# Usage: TAG=<git sha> ./deploy.sh        Roll back: TAG=$(cat .previous_tag) ./deploy.sh
# Migrations are forward-only and must stay backward compatible with the previous release (expand → migrate →
# contract across two releases), so rolling back images never requires rolling back the schema.
set -eu
: "${TAG:?set TAG to the image tag (git sha) to deploy}"
export TAG
compose="docker compose -f docker-compose.prod.yml"
$compose pull
$compose --profile migrate run --rm migrate
$compose up -d --remove-orphans
for i in $(seq 1 30); do
  if curl -fsS "https://${DOMAIN:-localhost}/ready" >/dev/null 2>&1; then break; fi
  [ "$i" = 30 ] && { echo "API not ready after deploy of $TAG" >&2; exit 1; }
  sleep 2
done
[ -f .deployed_tag ] && cp .deployed_tag .previous_tag
echo "$TAG" > .deployed_tag
echo "deployed $TAG"
