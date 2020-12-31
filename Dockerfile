###############################################################################
# api_server
FROM python:2.7.16-buster

# setup aliases for bash
RUN echo 'alias c="clear"' >> /root/.bashrc
RUN echo 'alias ll="ls -lah"' >> /root/.bashrc
RUN echo 'alias lc="c; ll"' >> /root/.bashrc

# install linux packages
RUN apt-get update

# install pip and python packages
RUN pip install --no-cache-dir --upgrade pip
COPY ./requirements.txt /srv/app/requirements.txt

# install required python packages
RUN pip install --no-cache-dir -r /srv/app/requirements.txt

# set ENV defaults, which can be overriden at run-time.
ENV PYTHONUNBUFFERED=1
ENV PYTHONPATH="/srv/app/src:/usr/local/lib/python2.7/site-packages"
ENV FLASK_APP="nupredictor/nunetwork.py"
ENV FLASK_ENV="development"
ENV NUPIC_MODEL_DIR="/srv/app/src/nupredictor/model_input_files"
ENV PROJECT_ROOT_DIR="/srv/app"

# copy project code files into docker image
WORKDIR "/srv/app/src"
ADD . /srv/app/

# entry point
CMD ["flask", "run", "--host=0.0.0.0"]
ENTRYPOINT ["/srv/app/scripts/docker-entrypoint.sh"]