### BEGIN INIT INFO
# Provides: nupredict
# Default-Start: 2 3 4 5
# Default-Stop: 0 1 6
# Required-Start: $all
# Description: Nupic Predictor (nupredict)
### END INIT INFO

PID_FILE="/var/run/nupredict.pid"


start() {
   su -c "/opt/predictors/nupic-predictor/nupredictor/services/start_nupredict.sh &" - bamboo
   echo $!>$PID_FILE
}

stop() {
   kill `cat $PID_FILE`
   rm $PID_FILE
}

status() {
   if [ -e $PID_FILE ]; then
      echo Nupic predictor is running, pid=`cat $PID_FILE`
   else
      echo Nupic predictor is stopped
      exit 1
   fi
}

restart() {
   $0 stop
   $0 start
}

case "$1" in
start)
   start
   ;;
stop)
   stop
   ;;
restart)
   restart
   ;;
status)
   status
   ;;
*)
   echo "Usage: $0 {start|stop|status|restart}"
esac

exit 0
