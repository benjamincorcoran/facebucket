python3 ./bucket.py 2>&1 | tee ./logs/$(date +"%Y-%m-%d-bucket.log")

/sbin/shutdown -r now
