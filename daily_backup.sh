tar -czvf $(date +"%Y-%m-%d")_bucket_backup.tar.gz ./*.json ./*.py

aws s3 cp *_bucket_backup.tar.gz s3://facebucket-backup/

rm *_bucket_backup.tar.gz
