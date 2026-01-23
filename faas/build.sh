#! /bin/bash
set -ex
cd `dirname $0`

rm -rf .next node_modules
# check dependencies
npm install
# output: 'standalone'
npm run build

# https://nextjs.org/docs/pages/api-reference/config/next-config-js/output#automatically-copying-traced-files
cp -r public .next/standalone/ && cp -r .next/static .next/standalone/.next/

rm -rf node_modules

rm -rf .next/cache