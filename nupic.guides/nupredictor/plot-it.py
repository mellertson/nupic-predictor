import matplotlib
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from datetime import datetime
from dateutil import parser


filename = '/opt/predictors/nupic.guides/nupredictor/results.csv'

df = pd.read_csv(filename, header=0)


# Data for plotting
epoch = datetime(1970,1,1)
t = [parser.parse(dt) for dt in list(df['Timestamp'])]
# t = np.arange(0.0, 2.0, 0.01)
# actual = [v for v in list(df.iloc[-50:]['Actual Change'])]
# predicted = [v for v in list(df.iloc[-50:]['Predicted Change'])]
score = [v for v in list(df['Score'])]

plt.subplot(1, 1, 1)
plt.plot(t, score, '-', linewidth=0.5)
plt.title('Score')
plt.ylabel('Awesome Shit yo!!')


plt.show()

