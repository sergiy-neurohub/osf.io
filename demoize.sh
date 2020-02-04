
cd osf.io
#docker ps |grep ember
#docker exec -it e46f0ff9d5f7 /bin/bash

docker-compose exec ember-osf-web


 sed -i 's/192.168.168.167/18.220.11.125/g' /code/config/environment.js
 sed -i 's/localhost/18.220.11.125/g' /code/config/environment.js

 
docker exec -it osfio_web_1 /bin/bash
cd website/settings
 sed -i 's/localhost/18.220.11.125/g' local.py
 sed -i 's/localhost/18.220.11.125/g' local.py
cd ~/osf.io/api/base
echo "ALLOWED_HOSTS = [   '.osf.io',    '18.220.11.125']" >> settings.py
      echo " "  >> ./node_modules/@glimmer/resolver/Brocfile.js


sed -i 's/localhost/18.220.11.125/g' .docker-compose.env
sed -i 's/localhost/18.220.11.125/g' .docker-compose.mfr.env
sed -i 's/localhost/18.220.11.125/g' .docker-compose.sharejs.env
sed -i 's/localhost/18.220.11.125/g' .docker-compose.wb.env

sed -i 's/192.168.168.167/18.220.11.125/g' .docker-compose.env
sed -i 's/192.168.168.167/18.220.11.125/g' .docker-compose.mfr.env
sed -i 's/192.168.168.167/18.220.11.125/g' .docker-compose.sharejs.env
sed -i 's/192.168.168.167/18.220.11.125/g' .docker-compose.wb.env






