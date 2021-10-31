from .functions import get_session
from .bucket import Bucket

if __name__=='__main__':

    session = get_session()
    bucket = Bucket(session)
    print('Bucket is running...')
    while True:
        try:
            bucket.run()
        except Exception as e:
            print(e)