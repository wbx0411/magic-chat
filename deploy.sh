# ./deploy.sh -m container -e test -p 27001 -h NO -v /app/docker -c NO

# Get parameters
while getopts ":m:e:p:h:u:w:v:c:" opt; do
    case $opt in
        m) RUN_MODE="$OPTARG"
        ;;
        e) RUN_ENV="$OPTARG"
        ;;
        p) RUN_PORT="$OPTARG"
        ;;
        h) HUB_URL="$OPTARG"
        ;;
        u) HUB_USER="$OPTARG"
        ;;
        w) HUB_PASS="$OPTARG"
        ;;
        v) VOL_PATH="$OPTARG"
        ;;
        c) VOL_SRC="$OPTARG"
        ;;
    esac
done

# container: run container only
if [ -z "$RUN_MODE" ]; then
  RUN_MODE=whole
fi

# environment
if [ -z "$RUN_ENV" ]; then
  echo ">> RUN_ENV is empty. Exiting"
  exit 1
fi

# host port
if [ -z "$RUN_PORT" ]; then
  echo ">> RUN_PORT is empty. Exiting"
  exit 1
fi

# docker hub url, NO for not upload
if [ -z "$HUB_URL" ]; then
  HUB_URL=10.0.87.150:15001
fi

# docker hub user
if [ -z "$HUB_USER" ]; then
  HUB_USER=dev
fi

# docker hub password
if [ -z "$HUB_PASS" ]; then
  HUB_PASS=neusoft
fi

# host file base path
if [ -z "$VOL_PATH" ]; then
  VOL_PATH=/app/docker/volume
fi

# volume source code, YES for source code, NO for config files
if [ -z "$VOL_SRC" ]; then
  VOL_SRC=NO
fi


# Define key variables
APP_NAME="magic-chat"
CONTAINER_NAME="$APP_NAME-$RUN_ENV"
IMG_NAME="neusoft/$APP_NAME"
TAG_NEW=$(date +'%Y%m%d%H')

# If build new image
if [ "$RUN_MODE" != "container" ]; then

  # Build new image and tags
  echo ">> Build new image $IMG_NAME"
  if ! docker build -t $IMG_NAME:latest .; then
    echo ">> Docker build failed. Exiting."
    exit 1
  fi

  echo ">> Tag image $IMG_NAME:$TAG_NEW"
  docker tag $IMG_NAME $IMG_NAME:$TAG_NEW

  if [ "$HUB_URL" != "NO" ]; then
    echo ">> Tag image $HUB_URL/$IMG_NAME"
    docker tag $IMG_NAME $HUB_URL/$IMG_NAME
    echo ">> Tag image $HUB_URL/$IMG_NAME:$TAG_NEW"
    docker tag $IMG_NAME $HUB_URL/$IMG_NAME:$TAG_NEW
  fi
fi


# Remove container
container_id=$(docker ps -a -q -f name=$CONTAINER_NAME)
if [ -n "$container_id" ]; then
  echo ">> Remove container $CONTAINER_NAME"
  # Stop the container if it is running
  docker stop $container_id
  # Remove the container
  docker rm $container_id
else
  echo ">> Check container $CONTAINER_NAME not exist"
fi


# Run container by environment
if [ "$VOL_SRC" = "YES" ]; then
  echo ">> Run new container $CONTAINER_NAME volume source code"
  # Run container by new image
  docker run -d --name $CONTAINER_NAME \
  -p $RUN_PORT:7002 \
  -e RUN_ENV=$RUN_ENV \
  -v $VOL_PATH/$APP_NAME:/app/src \
  $IMG_NAME:latest
else
  echo ">> Run container $CONTAINER_NAME"
  # Run container by new image
  docker run -d --name $CONTAINER_NAME \
  -p $RUN_PORT:7002 \
  -e RUN_ENV=$RUN_ENV \
  -v $VOL_PATH/$APP_NAME/configs/config.$RUN_ENV.yaml:/app/src/configs/config.$RUN_ENV.yaml \
  -v $VOL_PATH/$APP_NAME/configs/logging_config.yml:/app/src/configs/logging_config.yml \
  $IMG_NAME:latest
fi


# If remove old images and upload new image
if [ "$RUN_MODE" != "container" ]; then
  # Remove old image and upload new images
  image_ids=$(docker images --format "{{.Repository}}:{{.Tag}} {{.ID}}" | grep $IMG_NAME | grep -v -E ":latest|:$TAG_NEW" | awk '{print $2}' | sort | uniq)

  for image_id in $image_ids; do
    echo ">> Remove old image $IMG_NAME $image_id"
    docker rmi -f "$image_id"
  done

  if [ "$HUB_URL" != "NO" ]; then
    echo ">> Login $HUB_URL with $HUB_USER/$HUB_PASS"
    docker login -u $HUB_USER -p $HUB_PASS http://$HUB_URL
    echo ">> Push new image $HUB_URL/$IMG_NAME"
    docker push $HUB_URL/$IMG_NAME:$TAG_NEW
    docker push $HUB_URL/$IMG_NAME:latest
  fi
fi