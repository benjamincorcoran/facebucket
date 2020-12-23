aws s3 cp HELP.json s3://facebucket-backup/$(date +"%Y-%m-%d")_HELP.json

aws s3 cp ITEMS.json s3://facebucket-backup/$(date +"%Y-%m-%d")_ITEMS.json

aws s3 cp RESPONSES.json s3://facebucket-backup/$(date +"%Y-%m-%d")_RESPONSES.json
