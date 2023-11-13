import streamlit as st
import pandas as pd
import numpy as np
from sklearn.metrics import mean_squared_error, mean_absolute_error
from sklearn.preprocessing import StandardScaler

from prophet import Prophet
from prophet.diagnostics import cross_validation
from prophet.utilities import regressor_coefficients
import plotly.graph_objects as go

from keras.models import Sequential
from keras.layers import LSTM
from keras.layers import Dense
from scikeras.wrappers import KerasRegressor
from sklearn.model_selection import KFold
from sklearn.model_selection import train_test_split


def calculate_smape(actual, predicted): # Function to calculate "Symmetric Mean Absolute Percentage Error"
    return round(
        np.mean(
            np.abs(predicted - actual) / 
            ((np.abs(predicted) + np.abs(actual))/2)
        )*100, 2
    )


def calculate_mdape(actual, predicted): # Function to calculate "Median Absolute Percentage Error"
    return round(
        np.median(
            np.abs(predicted - actual) / 
            ((np.abs(predicted) + np.abs(actual))/2)
        )*100, 2
    )


def get_adi_cv2(series):
    
    total_periods=series.count()
    non_zero_periods=series.loc[series!=0].count()
    adi=total_periods/non_zero_periods
    
    non_zero_series=series.loc[series!=0]
    cv2=(np.std(non_zero_series)/np.mean(non_zero_series))**2
    
    return adi,cv2


def prepare_data_LSTM(df, n_steps_in, n_steps_out):

    scaler_X=StandardScaler()
    scaler_Y=StandardScaler()
    df.iloc[:,:-1]=scaler_X.fit_transform(np.array(df.iloc[:,:-1]))
    df.iloc[:,-1]=scaler_Y.fit_transform(np.array(df.iloc[:,-1]).reshape(-1,1))

    # df.drop(["ds"],axis=1,inplace=True) # Please Don't change anything in this Function. Changing anything will lead to Error in Code.

    sequences=np.array(df)

    X, y = list(), list()
    for i in range(len(sequences)):
        # find the end of this pattern
        end_ix = i + n_steps_in
        out_end_ix = end_ix + n_steps_out
        # check if we are beyond the dataset
        if out_end_ix > len(sequences):
            break
        # gather input and output parts of the pattern
        seq_x, seq_y = sequences[i:end_ix], sequences[end_ix:out_end_ix, -1]
        X.append(seq_x)
        y.append(seq_y)

    return np.array(X), np.array(y), scaler_X, scaler_Y


def prepare_test_data_LSTM(df, n_steps_in, n_steps_out, scaler_X):

    df.iloc[:,:] = scaler_X.transform(np.array(df))

    # df.drop(["ds"],axis=1,inplace=True) # Please Don't change anything in this Function. Changing anything will lead to Error in Code.

    sequences=np.array(df)

    X = list()
    for i in range(len(sequences)):
        # find the end of this pattern
        end_ix = i + n_steps_in

        # check if we are beyond the dataset
        if end_ix > len(sequences):
            break
            
        # gather input parts of the pattern
        seq_x = sequences[i:end_ix]
        X.append(seq_x)

    return np.array(X)


def recursive_forecasting(model,X,X_test,output_steps,input_steps):

    n=X_test.shape[0]+X_test.shape[1]-1 # Number of Future Dates for which we need to make Predictions.

    last_input=X[-1].reshape((-1,X[-1].shape[0],X[-1].shape[1]))

    y_pred=model.predict(last_input)
    y_predicted=y_pred.ravel() 
    # y_predicted will Contain 'n' values. One Predicted value for each Future Date. 


    lena=0 # From Which X_test we have to take the data point(regarding one date) and add it to last_input.
    if n>=output_steps:
        j=n-output_steps # Number of times we have to make Prediction after first Prediction using the last input from X_train/X.

        index_for_X_test=0 # Index that indicates which that which data point we need to take from 'lena' X_test
        for i in range(j): # In this For Loop we are taking a data point(regarding one date) from the X_test and adding it to last_input after all changes(Changes Include removing "ds" value from the 0th Index and adding y_pred value at the end index). 

            if index_for_X_test < input_steps:
                to_add=X_test[lena,index_for_X_test]
            else:
                lena+=1
                index_for_X_test=0
                to_add=X_test[lena,index_for_X_test]
            
            to_add=np.append(to_add,y_predicted[i]) # Adding the y_value
            to_add=to_add[1:]  # Removing the "ds" element.

            last_input=np.concatenate((last_input, to_add.reshape(1,1,X.shape[-1])), axis=1) # Adding 'to_add' to the last_input.
            last_input=last_input[:,1:,:] # Removing the 1st data point(regarding a single date) from last_input.
            
            y_pred=model.predict(last_input)

            y_predicted=np.append(y_predicted, y_pred.ravel()[-1])

            index_for_X_test+=1
    
    # print(y_predicted)
    return y_predicted




                


def build_model(layers, activation, recurrent_activation, input_steps, features, output_steps):
    model = Sequential()

    for i in range(layers):
        
        if i==layers-1 and layers==1:
            model.add(LSTM(int(st.session_state[f"layer_{i}_CellState"]), activation=activation, recurrent_activation=recurrent_activation, return_sequences=False, input_shape=(input_steps, features)))
        elif i==layers-1:
            model.add(LSTM(int(st.session_state[f"layer_{i}_CellState"]), activation=activation, recurrent_activation=recurrent_activation, return_sequences=False))
        elif i==0:
            model.add(LSTM(int(st.session_state[f"layer_{i}_CellState"]), activation=activation, recurrent_activation=recurrent_activation, return_sequences=True, input_shape=(input_steps, features)))
        else:
            model.add(LSTM(int(st.session_state[f"layer_{i}_CellState"]), activation=activation, recurrent_activation=recurrent_activation, return_sequences=True))

    model.add(Dense(output_steps))

    model.compile(optimizer='adam', loss='mse')

    return model




st.markdown(
    """<style>
div[class*="stRadio"] > label > div[data-testid="stMarkdownContainer"] > p {
    font-size: 25px;
}
    </style>
    """, unsafe_allow_html=True)



def convert_df(df):
    # IMPORTANT: Cache the conversion to prevent computation on every rerun
    return df.to_csv().encode('utf-8')




st.set_option('deprecation.showPyplotGlobalUse', False) # to prevent display of warnings
st.title("Time Series Forecasting for Different Demand Patterns") # Heading of App.
st.sidebar.image("https://www.analyticssteps.com/backend/media/thumbnail/6350483/7807104_1578230927_time_analysis_tittle-banner%20(1).jpg") # Adding Image to the Sidebar.





# TAKING INPUT FROM USER (Same For Both FB-Prophet and LSTMs)

####################################################################################################################################

st.sidebar.header("1. DATA")

with st.sidebar.expander("Uploading Dataset",expanded=True): # Exapander inside Sidebar for UPLOADING DATA

    default_data=st.checkbox("Use Demo Dataset", value=False,key="default data")

    upload = st.file_uploader("Upload File", type={"csv"}) # File Uploader

    if upload is not None: # Checking if File is uploaded or not, If Something is Uploaded then only the "if" condition gets satisfied.
        df = pd.read_csv(upload,index_col=0) # Reading the CSV file as 'df' DataFrame. There should be one index like column in data other than Date and other important columns.
        df2 = df.copy()  #  'df2' is initialized so that we can always have a copy of Original Uploaded Dataset. All processing will be done on 'df'
    
    
    if default_data==True:
        df=pd.read_csv("trial_dataset2.csv", index_col=0)
        df2=df.copy()
        upload=1


with st.sidebar.expander("Info About Data"):

    if upload is not None:
        date_column=st.selectbox("Please Select Date Column",df.columns.to_list(),index=1 if default_data else 0) # The User has to select the Column name that has Dates/Time in the Time Series Data.
        date_format=st.text_input("What is the Date Format", value=r"%Y-%m-%d", help=r"For example '%Y-%m-%d' or '%d/%m/%Y %H:%M:%S'") # User has to mention the format in which Date is there in the Date Column. 
        target_column=st.selectbox("Please Select Target Column",df.columns.to_list(), index=2 if default_data else 0) # The User has to select the Target column/y_variable which will be varying with Time and whose value has to be forecasted.
    
        freq_unit=st.selectbox("Unit of time present in time Series Data",["days","hours","minutes","seconds"])  # the frequency unit of Time Series data.
        freq=st.number_input(f"Frequency of Time Series in {freq_unit}",value=7.0 if default_data else 1.0,min_value=0.0) # Magnitude of frequency in 'freq_unit'.
        
        
with st.sidebar.expander("Filtering Data"): # Exapander inside Sidebar for FILTERING DATASET

    if upload is not None:  # Checking if File is uploaded or not, If Something is Uploaded then only the "if" condition gets satisfied.
        cat_cols = st.multiselect("Select Categorical Columns for Filtering Dataset",df.columns.to_list(), help='''Prophet can only forecast one series at a time. In case your dataset contains several time series, you might want to filter or aggregate these different series. 
                Dimensions are the Categorical Columns on which the dataset can be filtered and aggregated on. In case no dimension is selected, all target values at the same date will be aggregated in order to get one target value per date. 
                Example: For a dataset containing sales from 3 countries A, B and C, you could select countries B and C, and forecast the sum of their sales.''')
        # 'cat_cols' represent list containing Independent Categorical Features on which Data is to be filtered as per User's requirement.


        col_list=[st.checkbox(f"Keep all values for '{i}'", value=True, help=f"Check to keep all values or uncheck to filter values on column '{i}'.", key=f'{i}') for i in cat_cols] # 'key' parameter is used so that we can access the value of the streamlit object again using 'session_state'. Every streamlit object's value can be accessed using 'key' parameter.
        # 'col_list' contains checkboxes for all Categorical columns selected in 'cat_cols' multiselect object.
        for j in range(len(col_list)): # If we uncheck a checkbox (present in 'col_list') corresponding to a column in "cat_cols", then for that column a multiselect object is created that is used for selecting values from that column for filtering Data.
            if not col_list[j]:
                col=cat_cols[j]
                st.multiselect(f"Values for '{col}'",df[col].unique(),key=f'{col}m') # 'key' parameter is used so that we can access the value of this streamlit object somewhere else, using 'session_state' method. Every streamlit object's value can be accessed using it unique 'key' parameter.
                    

        num_cols=st.multiselect("Select Numerical Independent Features that are to be Aggregated",df.columns.to_list(), help="Numerical Columns which will be aggregated so that a Single Time Series can be made. Add Columns that will be used as Extra Regressors.") # Many numerical columns, present in data, that may be used as regressors are specified here.
        agg_func_list=[st.selectbox(f"Aggregation Function for '{col}'",["mean","sum","min","max","median"], key=f"{col} agg") for col in num_cols] # Aggregation function for every column added in "num_cols" is specified here. We create a selectbox object for every column mentioned in 'num_cols' object.

        y_variable_agg_func=st.selectbox(f"Aggregation Function for '{target_column}'",["mean","sum","min","max","median"])  # Even after filtering the dataset based on columns in 'cat_cols', if we don't get one y value for one date value, then we need to aggregate the y_variable using the aggregation function mentioned in 'y_variable_agg_func'.





# We need to check everytime whether 'upload' is None or not, i.e whether the User has uploaded the Data or not. If the User hasn't uploaded the Data then we need not calculate/display anything on the site. 
if upload is not None:
    filter_button=st.sidebar.checkbox("Apply Filter to Dataset",value=True if default_data else False) # Only After checking this button all the filtering, that user mentioned in different containers of DATA and MODELLING sections, takes place on the Dataset that user uploaded in "Uploading Datset" container.

    
    adi_value,cv2_value=get_adi_cv2(df[target_column])
    adi,cv2=st.columns(2)

    adi.metric("**:red[ADI]**", f"{round(adi_value,2)}")
    cv2.metric("**:red[CV Squared]**", f"{round(cv2_value,2)}")

    if adi_value<1.32 and cv2_value<0.49:
        classification="SMOOTH PATTERN"
    elif adi_value>=1.32 and cv2_value<0.49:
        classification="INTERMITTENT PATTERN"
    elif adi_value<1.32 and cv2_value>=0.49:
        classification="ERRATIC PATTERN"
    else:
        classification="LUMPY PATTERN"

    st.subheader(body=f"The Data Shows : {classification}")
    st.write("To read about Demand Classification, ADI and CV2 in Detail Check Out : [Link](https://frepple.com/blog/demand-classification/)")


###############################################################################################################################################



# MAKING A CHOICE (WHETHER TO USE LSTM or FB-Prophet)
if upload is not None:
    algo=st.radio(label="Choose any One Algorithm for Forecasting",options=["Fb-Prophet","LSTMs"])
else:
    algo=None



# From Here things are different for LSTMs and FB-Prophet.



###                                                     CODE FOR FB-PROPHET 
#########################################################################################################################################
#########################################################################################################################################
#########################################################################################################################################

    

if algo=="Fb-Prophet":


    ####################################################################################################################################
    
    # TAKING INPUT FROM USER (INPUT SPECIFIC TO FBPROPHET MODEL)

    #######################################################################################################################################


    if upload is not None:
        st.sidebar.header("2. MODELLING")

    with st.sidebar.expander("Change Point Detection"):  # Exapander inside Sidebar for change_point_detection

        if upload is not None: # Checking if File is uploaded or not, If Something is Uploaded then only the "if" condition gets satisfied.
            # Parameters that affect the trend/changepoint detection in Prophet Model
            change_point_prior_scale=st.number_input("Change_Point_Prior_Scale", min_value=0.0, value=0.050, help="Prophet automatically detects changepoints in the trend.\nThis parameter determines trend flexibility by adjusting the number of changepoints detected.\nIf you make it high, the trend will be more flexible (more changepoints), and Vice Versa")
            change_point_range=st.number_input("Change_Point_Range", min_value=0.0, value=0.8,max_value=1.0, help="Proportion of history in which trend changepoints will be estimated. Defaults to 0.8 for the first 80%.")
            n_change_points=st.number_input("n_change_points", min_value=1, value=25, help="Number of potential changepoints to include.")
            growth_pattern=st.selectbox("Growth_Pattern",["linear","flat","logistic"], index=0, help="Specify the Pattern of Growth/Declination")
            if growth_pattern=="logistic": # If the Growth Pattern is 'logistic' then we need to add columns 'cap','floor' in our dataset that mentions a max_value and min_value of Prediction for every row, that 'cap','floor' value is mentioned in 'cap_value','floor_value' streamlit object respectively.
                cap_value=st.number_input("cap_value",value=10.0, help="If the Growth_Pattern is 'Logisitic', then you need to specify the max prediction value of y variable.")
                floor_value=st.number_input("floor_value",value=1.0, help="If the Growth_Pattern is 'Logisitic', then you need to specify the min prediction value of y variable.")


    # Parameters that set the Seasonality aspect in Prophet Model       
    with st.sidebar.expander("Seasonalities"):  # Exapander inside Sidebar for Seasonalities

        if upload is not None:    
            
            daily_seasonality=st.selectbox("Daily_Seasonality",["auto", False], index=1, help="Choose whether or not to include this seasonality in the model. In 'auto' mode, Prophet will include a seasonality only if there are at least 2 full periods of historical data (for example 2 years of data for yearly seasonality).")
            # daily seasonality means seasonality in a cycle from 12am one day to 12am another day i.e a period of 24hrs.


            weekly_seasonality=st.selectbox("Weekly_Seasonality",["auto", False, "Custom"], index=0, help="Choose whether or not to include this seasonality in the model. In 'auto' mode, Prophet will include a seasonality only if there are at least 2 full periods of historical data (for example 2 years of data for yearly seasonality).")
            # weekly seasonality by default means seasonality in a cycle from Sunday to Saturday and not any other consecutive 7 days. For any other consecutive 7 days, for example from Wednesday to next Tuesday, we need to add custom seasonality.
            if weekly_seasonality=="Custom":
                mode_w=st.selectbox("Mode for Weekly Seasonality", ["additive","multiplicative"], index=0, help="Determines how seasonality components should be integrated with the predictions:\nUse 'additive' when seasonality trend should be “constant” over the entire period (typically for linear trends).\nUse 'multiplicative' to increase the importance of the seasonality over time (typically for exponential trends).")
                fourier_order_w=st.number_input("Fourier Order for Weekly Seasonality", value=7, min_value=1, help="Each seasonality is a fourier series as a function of time. The fourier order is the number of terms in the series. A higher order can fit more complex and quickly changing seasonality patterns, but it will also make overfitting more likely. You can use the seasonality components plots of this app to tune this parameter visually.")
                prior_scale_w=st.number_input("Prior_Scale for Weekly Seasonality", value=10.0, min_value=1.0, help="Determines the magnitude of seasonality effects on your predictions. Decrease this value if you observe that seasonality effects are overfitted.")
                weekly_seasonality_value=False
            else:
                weekly_seasonality_value=weekly_seasonality


            yearly_seasonality=st.selectbox("Yearly_Seasonaltiy",["auto", False, "Custom"], index=0, help="Choose whether or not to include this seasonality in the model. In 'auto' mode, Prophet will include a seasonality only if there are at least 2 full periods of historical data (for example 2 years of data for yearly seasonality).")
            # yearly seasonality by default means seasonality in a cycle from January 1 to December 31 and not any other period of 365 days. For any other period of 365 days, example for June 30 2021 to June 30 2022, we need to add custom seasonality.
            if yearly_seasonality=="Custom":
                mode_y=st.selectbox("Mode for Yearly Seasonality", ["additive","multiplicative"], index=0, help="Determines how seasonality components should be integrated with the predictions:\nUse 'additive' when seasonality trend should be “constant” over the entire period (typically for linear trends).\nUse 'multiplicative' to increase the importance of the seasonality over time (typically for exponential trends).")
                fourier_order_y=st.number_input("Fourier Order for Yearly Seasonality", value=7, min_value=1, help="Each seasonality is a fourier series as a function of time. The fourier order is the number of terms in the series. A higher order can fit more complex and quickly changing seasonality patterns, but it will also make overfitting more likely. You can use the seasonality components plots of this app to tune this parameter visually.")
                prior_scale_y=st.number_input("Prior_Scale for Yearly Seasonality", value=10.0, min_value=1.0, help="Determines the magnitude of seasonality effects on your predictions. Decrease this value if you observe that seasonality effects are overfitted.")
                yearly_seasonality_value=False
            else:
                yearly_seasonality_value=yearly_seasonality

            
            add_custom_seasonality=st.checkbox("Add a Custom Seasonality in Model", help="Check to add a Custom Seasonality in Model (Other than ones listed above)")
            if add_custom_seasonality: # if 'add_custom_seasonality' is checked then this 'if' condition gets satisfied.
                name_c=st.text_input("Name of Seasonality", help="Give a Name for Your Custom Seasonality", value="Custom_Seasonality") # Specify the name of the custom Seasonality.
                period_c=st.number_input("Periods (in Days)", min_value=1, value=30, help="Number of days of each cycle.") # Period of Seasonality, means the length of 1 cycle of seasonality.
                mode_c=st.selectbox("Mode", ["additive","multiplicative"], index=0, help="Determines how seasonality components should be integrated with the predictions:\nUse 'additive' when seasonality trend should be “constant” over the entire period (typically for linear trends).\nUse 'multiplicative' to increase the importance of the seasonality over time (typically for exponential trends).")
                fourier_order_c=st.number_input("Fourier Order", value=7, min_value=1, help="Each seasonality is a fourier series as a function of time. The fourier order is the number of terms in the series. A higher order can fit more complex and quickly changing seasonality patterns, but it will also make overfitting more likely. You can use the seasonality components plots of this app to tune this parameter visually.")
                prior_scale_c=st.number_input("Prior_Scale", value=10.0, min_value=1.0, help="Determines the magnitude of seasonality effects on your predictions. Decrease this value if you observe that seasonality effects are overfitted.")


    with st.sidebar.expander("Regressors"): # Expander inside sidebar for adding Regressors in Prophet Model.(For Multivariate Time Series Analysis)

        if upload is not None:

            regressors=st.multiselect("Add Regressors that affect y_variable", df.columns.to_list(), help="Add Numerical columns that have impact on value of y_variable.",default=num_cols)
            regressors_prior_scale=[st.number_input(f"Prior Scale for '{col}' regressor", value=10.0, min_value=1.0, help="Determines the magnitude of the regressor effect on your predictions.", key=f"{col} reg") for col in regressors]
            # regressors_prior_scale is a list of number_input objects for each regressor that have been added to 'regressors' multiselect object.




    # Parameters that help in Model Evaluation.(Train test Splitting or Cross Validation)  
    if upload is not None:
        st.sidebar.header("3. MODEL EVALUATION")

    with st.sidebar.expander("Train/Validation Splitting Or Cross Validation"):

        if upload is not None:

            cross_validation_=st.checkbox("Perform Cross Validation", value=False, help="Check to evaluate performance through a cross-validation, or uncheck to use a simple training/test split.") # Checkbox for performing Cross Validation or doing Simple Train-Test Split.

            if cross_validation_:
                cv=st.number_input("Number of CV Folds", value=5, min_value=2, help="Number of distinct training/validation pairs to include in the cross-validation.")
                horizon=st.number_input("Horizon of each Fold", value=10, min_value=2, help="Length of Validation period for each fold.")
                # This cross validation procedure can be done automatically for a range of historical cutoffs using the cross_validation function. We specify the forecast horizon (horizon), and then optionally the size of the initial training period (initial) and the spacing between cutoff dates (period). By default, the initial training period is set to three times the horizon, and cutoffs are made every half a horizon.
                # The output of cross_validation is a dataframe with the true values y and the out-of-sample forecast values yhat, at each simulated forecast date and for each cutoff date. In particular, a forecast is made for every observed point between cutoff and cutoff + horizon. This dataframe can then be used to compute error measures of yhat vs y.
                test_size=0

            else:   # If the user doesn't opts for Cross_Validation then he/she has to mention the test_size for the data Uploaded. 
                test_size=st.number_input("Test Size in Percentage of Total Data", value=20.0, min_value=0.0, max_value=100.0)*0.01 # The user should Input the Test Size as percentage of size of CSV file Uploaded.




    if upload is not None:
        forecast_button=st.sidebar.checkbox("Make Forecast for Future Dates", value=False) 
        # If the User wants to get the forecast on Future dates (Which are not there in the initial Uploaded Dataset), then he/she has to check the 'forecast_button'.
        # If the 'forecast_button' is checked by the the user, then whole of the data uploaded by the user will be used for Training the Model and error/metrics will be calculated only on Training Data.



    if upload is not None and forecast_button:
        st.sidebar.header("4. MAKE FORECAST")


    with st.sidebar.expander("Forecasting on Future Dates",expanded=True):

        if upload is not None and forecast_button: 
            
            if len(regressors)>0:

                st.write("Upload Test Data CSV file having the same Schema as the Training data CSV file.")
                test_upload=st.file_uploader("Upload Test Data", type={"csv"})


                if test_upload is not None:
                    test_data=pd.read_csv(test_upload, index_col=0) # There should be one index like column in data other than Date and other important columns.
                    test_data2=test_data.copy()

            else:

                upload_test_data=st.checkbox("Upload Test Data")

                if upload_test_data:

                    st.write("Upload Test Data CSV file having the same Schema as the Training data CSV file.")
                    test_upload=st.file_uploader("Upload Test Data", type={"csv"})


                    if test_upload is not None:
                        test_data=pd.read_csv(test_upload,index_col=0) # There should be one 'index like column' in data other than Date and other important columns. 'index_col=0' makes the first column of data as the 'index'. 
                        test_data2=test_data.copy()
                
                else:

                    future_forecast_period=st.number_input("Future Forecast Period", help="Number of Future Dates on which Forecast is to be made", min_value=1, value=10)

                    


    ######################################################################################################################################                


    # MODIFYING DATA AND TRAINING MODEL BASED ON USER INPUT.

    ####################################################################################################################################


    ## Modifying 'df' dataframe. All the filters and modifications that are specified in "Filtering Data" and "Info About Data"
    if upload is not None:          # Checking if File is uploaded or not, If Something is Uploaded then only the "if" condition gets satisfied.
        if filter_button:           # If checkbox of Filter button is pressed, then only this 'if' condition gets satisfied and all filtering/processing of Uploaded dataset takes place.

            df[date_column]=pd.to_datetime(df[date_column], format=date_format) # Changing Data Type of Date Column to DateTime.
            dates=df[date_column].unique()

            for i in cat_cols:      # This loop iterates for all column names present in 'cat_cols' multiselect object and checks whether the checkbox corresponding to the particular column is checked or not.  
                if not st.session_state[i] and len(st.session_state[i+'m'])>0:  # If the checkbox (present in 'col_list') corresponding to a column name (present in 'cat_cols') is unchecked and there are more than 0 values in the multiselect object (made as the checkbox for that column was unchecked) corresponding to that column, then we filter the dataset using the values mentioned in that multiselect object.
                    df=df.loc[df[i].isin(st.session_state[i+'m'])]


            agg_funcs_for_num_cols=[st.session_state[col+" agg"] for col in num_cols] # Making a list of aggregation functions for each column mentioned in 'num_cols' object.
            diction=dict(zip(num_cols,agg_funcs_for_num_cols))                        # Making a dictionary that contains column name (present in 'num_cols') as key and its aggregation function (present in 'agg_funcs_for_num_cols') as its value.

            

            dates_present_after_filter=df[date_column].unique()

            if set(dates)!=set(dates_present_after_filter):

                filtered_out_dates=pd.DataFrame({date_column:[date for date in dates if date not in dates_present_after_filter]})
                if len(diction)>0:
                    aggregations=df.agg(diction)
                df=pd.concat([df,filtered_out_dates], ignore_index=True)

                for col in num_cols:
                    df[col].replace(np.nan, aggregations.loc[col], inplace=True)
                df[target_column].replace(np.nan, 0, inplace=True)
            
            

            diction[target_column]=y_variable_agg_func               # Adding a new key-value pair in the 'diction' dictionary, the new key-value pair is of y_variable and its aggregation function.

            df=df.groupby([date_column]).agg(diction).reset_index()  # This groups the data according to Date column and thus now we get one y value for one Date value, therefore only 1 Time Series.

            df.rename(columns={str(date_column): "ds", str(target_column):"y"}, inplace=True) # Just changing name of Date and target column to "ds" and "y" as its needed for Training of Prophet Model.

            if growth_pattern=="logistic": # If growth pattern is logistic then we need to mention 'cap' value for every row in dataset.
                df["cap"]=cap_value        # Here we are making new columns in 'df' named as 'cap' and 'floor' that has value contained in 'cap_value' and 'floor_value' respectively.
                df["floor"]=floor_value
            else:                          # On changing growth pattern from 'logistic' to any other growth pattern, we need to drop the 'cap','floor' column from the dataset 'df' therefore we have used df.drop() function. But considering the Case when we initially chose 'linear'/'flat' growth pattern then for that case df.drop() will raise a 'KeyError', thus we have used exception handelling. 
                try:
                    df.drop(["cap","floor"], axis=1, inplace=True)
                except KeyError:
                    pass
            

            st.write("#")
            st.write("#")
            st.write("#")

            st.table(df.head())
            st.write(f'<p style="font-size:26px;">Uploaded data has {df.ds.nunique()} unique Date Values</p>', unsafe_allow_html=True)


        else:  # This 'else' section is to restore the processed/filtered dataset to its original uploaded form when we uncheck the 'filter_button'.
            df=df2



    # Modifying Test Data Uploaded by User (In the Same Format as Training Data was modified as above)
    if upload is not None:

        if forecast_button:

            if len(regressors)>0 or upload_test_data:

                if test_upload is not None:

                    if filter_button:
                    
                        test_data[date_column]=pd.to_datetime(test_data[date_column], format=date_format)
                        test_dates=test_data[date_column].unique()
                        

                        for i in cat_cols:      # This loop iterates for all column names present in 'cat_cols' multiselect object and checks whether the checkbox corresponding to the particular column is checked or not.  
                            if not st.session_state[i] and len(st.session_state[i+'m'])>0:  # If the checkbox (present in 'col_list') corresponding to a column name (present in 'cat_cols') is unchecked and there are more than 0 values in the multiselect object (made as the checkbox for that column was unchecked) corresponding to that column, then we filter the dataset using the values mentioned in that multiselect object.
                                test_data=test_data.loc[test_data[i].isin(st.session_state[i+'m'])] 

                        agg_funcs_for_num_cols_forecast=[st.session_state[col+" agg"] for col in num_cols] # Making a list of aggregation functions for each column mentioned in 'num_cols' object.
                        diction_forecast=dict(zip(num_cols, agg_funcs_for_num_cols_forecast))              # Making a dictionary that contains column name (present in 'num_cols') as key and its aggregation function (present in 'agg_funcs_for_num_cols') as its value. 



                        test_dates_present_after_filter=test_data[date_column].unique()

                        if set(test_dates)!=set(test_dates_present_after_filter):

                            filtered_out_test_dates=pd.DataFrame({date_column:[date for date in test_dates if date not in test_dates_present_after_filter]})
                            if len(diction_forecast)>0:
                                aggregations=test_data.agg(diction_forecast)
                            test_data=pd.concat([test_data, filtered_out_test_dates], ignore_index=True)

                            for col in num_cols:
                                test_data[col].replace(np.nan, aggregations.loc[col], inplace=True)

                        
                        if len(diction_forecast)>0:
                            test_data=test_data.groupby([date_column]).agg(diction_forecast).reset_index()  # This groups the data according to Date column and thus now we get one y value for one Date value, therefore only 1 Time Series.
                        else: ## Adding this else statement ensures that even if len(diction_forecast)==0, the test_data will be finally having no repeated date values.
                            test_data.drop_duplicates(subset=date_column,inplace=True, ignore_index=True)

                        test_data.rename(columns={str(date_column): "ds"}, inplace=True) # Just changing name of Date and target column to "ds" and "y" as its needed for Training of Prophet Model.

                        if growth_pattern=="logistic": # If growth pattern is logistic then we need to mention 'cap' value for every row in dataset.
                            test_data["cap"]=cap_value        # Here we are making new columns in 'test_data' named as 'cap' and 'floor' that has value contained in 'cap_value' and 'floor_value' respectively.
                            test_data["floor"]=floor_value
                        else:                          # On changing growth pattern from 'logistic' to any other growth pattern, we need to drop the 'cap','floor' column from the dataset 'test_data' therefore we have used test_data.drop() function. But considering the Case when we initially chose 'linear'/'flat' growth pattern then for that case test_data.drop() will raise a 'KeyError', thus we have used exception handelling. 
                            try:
                                test_data.drop(["cap","floor"], axis=1, inplace=True)
                            except KeyError:
                                pass

                    else:
                        test_data=test_data2





    ## Fitting Data to the Model along with Hyperparameters mentioned in Above Sections.
    if upload is not None:

        launch=st.checkbox("Launch Model",value=True if default_data else False, help="Check to launch forecast. A new forecast will be made each time some parameter is changed in the sidebar.")

        if launch and filter_button:

            model=Prophet(changepoint_prior_scale=change_point_prior_scale, changepoint_range=change_point_range, n_changepoints=n_change_points, growth=growth_pattern,
                        yearly_seasonality=yearly_seasonality_value, weekly_seasonality=weekly_seasonality_value, daily_seasonality=daily_seasonality)
            model_temp=model

        
            if weekly_seasonality=="Custom":
                model.add_seasonality(name="Weekly_Seasonality", fourier_order=fourier_order_w, period=7.0, prior_scale=prior_scale_w, mode=mode_w)
            else:
                model=model_temp

            
            if yearly_seasonality=="Custom":
                model.add_seasonality(name="Yearly_Seasonality", fourier_order=fourier_order_y, period=365.0, prior_scale=prior_scale_y, mode=mode_y)
            else:
                model=model_temp

            
            if add_custom_seasonality:
                model.add_seasonality(name=name_c, fourier_order=fourier_order_c, period=period_c, prior_scale=prior_scale_c, mode=mode_c)
            else:
                model=model_temp
            
            
            for col in regressors:
                model.add_regressor(name=col, prior_scale=st.session_state[col+" reg"])
            

            model_temp_2=model


            if forecast_button:

                model=model_temp_2
                model.fit(df)

                if cross_validation_:
                    initial_size=len(df["ds"].values[0:-int(horizon*cv)-cv])  # [Total Data Size - (Horizon*cv)] = initial data size (Given Period = Horizon)
                    df_cv = cross_validation(model, horizon=str(int(horizon*freq))+f" {freq_unit}", period=str(int(horizon*freq))+f" {freq_unit}", initial=str(int(initial_size*freq))+f" {freq_unit}")


                if len(regressors)>0 and test_upload is not None:

                    future=model.make_future_dataframe(periods=test_data["ds"].count(), freq=pd.Timedelta(f"{float(freq)} " + freq_unit))

                    for col in regressors:
                        future[col]=pd.concat([df[col], test_data[col]]).reset_index(drop=True)

                    if growth_pattern=="logistic":
                        future["cap"]=cap_value
                        future["floor"]=floor_value
                    else:
                        try:
                            future.drop(["cap","floor"], axis=1, inplace=True)
                        except KeyError:
                            pass
            
                    forecast=model.predict(future)


                elif len(regressors)==0 and upload_test_data and test_upload is not None:
                    
                    future=model.make_future_dataframe(periods=test_data["ds"].count(), freq=pd.Timedelta(f"{float(freq)} " + freq_unit))

                    if growth_pattern=="logistic":
                        future["cap"]=cap_value
                        future["floor"]=floor_value
                    else:
                        try:
                            future.drop(["cap","floor"], axis=1, inplace=True)
                        except KeyError:
                            pass
            
                    forecast=model.predict(future)


                elif len(regressors)==0 and not upload_test_data:

                    future=model.make_future_dataframe(periods=future_forecast_period, freq=pd.Timedelta(f"{float(freq)} " + freq_unit))

                    if growth_pattern=="logistic":
                        future["cap"]=cap_value
                        future["floor"]=floor_value
                    else:
                        try:
                            future.drop(["cap","floor"], axis=1, inplace=True)
                        except KeyError:
                            pass
            
                    forecast=model.predict(future)



            else:

                if cross_validation_:
                    model=model_temp_2
                    initial_size=len(df["ds"].values[0:-int(horizon*cv)-cv])  # [Total Data Size - (Horizon*cv)] = initial data size (Given Period = Horizon)
                    model.fit(df)
                    df_cv = cross_validation(model, horizon=str(int(horizon*freq))+f" {freq_unit}", period=str(int(horizon*freq))+f" {freq_unit}", initial=str(int(initial_size*freq))+f" {freq_unit}")
                    future=model.make_future_dataframe(periods=0, freq=pd.Timedelta(f"{float(freq)} " + freq_unit))


                    if growth_pattern=="logistic":
                        future["cap"]=cap_value
                        future["floor"]=floor_value
                    else:
                        try:
                            future.drop(["cap","floor"], axis=1, inplace=True)
                        except KeyError:
                            pass
                
                    for col in regressors:
                        future[col]=df[col]

                    forecast=model.predict(future)
                    

                else:
                    model=model_temp_2
                    model.fit(df.iloc[:int(df["ds"].count()*(1-test_size))])
                    future=model.make_future_dataframe(periods=len(df.iloc[int(df["ds"].count()*(1-test_size)):,0]), freq=pd.Timedelta(f"{float(freq)} " + freq_unit))

                    if growth_pattern=="logistic":
                        future["cap"]=cap_value
                        future["floor"]=floor_value
                    else:
                        try:
                            future.drop(["cap","floor"], axis=1, inplace=True)
                        except KeyError:
                            pass
                
                    for col in regressors:
                        future[col]=df[col]

                    forecast=model.predict(future)
                
    ######################################################################################################################################


    # OUTPUT DISPLAYED TO THE USER BASED ON HIS/HER INPUT. DISPLAYES THE FORESCAST/HOW THE MODEL PERFORMED.

    ####################################################################################################################################

    if upload is not None:
        
        if launch and filter_button:

            st.subheader("1. Overview") # Adding Forecast Figure (Overview of Prophet Model)

            trace1=go.Scatter(
                x=df["ds"],
                y=df["y"],
                mode="lines",
                name="Actual Value",
                line=dict(color='rgb(244, 24, 231)', width=2)
            )


            if forecast_button and ( (len(regressors)>0 and test_upload is not None) or (len(regressors)==0 and not upload_test_data) or (len(regressors)==0 and upload_test_data and test_upload is not None) ):

                trace2=go.Scatter(
                    x=df["ds"],
                    y=forecast.iloc[:df["ds"].count()]["yhat"],
                    mode="lines+markers",
                    name="Predicted Values on Training Data",
                    line=dict(color='rgb(151, 51, 30)', width=2)
                )
                trace3=go.Scatter(
                    x=forecast.iloc[df["ds"].count():]["ds"],
                    y=forecast.iloc[df["ds"].count():]["yhat"],
                    mode="lines+markers",
                    name="Forecasted Values on Future Dates",
                    line=dict(color='rgb(20, 161, 10)', width=2)
                )

                fig1=go.Figure()
                fig1.add_trace(trace1)
                fig1.add_trace(trace2)
                fig1.add_trace(trace3)

                fig1['layout'].update(height = 500, width = 900, title = "Forecasted Vs Actual Values")
                st.plotly_chart(fig1)
            

            elif not forecast_button:
        
                trace2=go.Scatter(
                    x=df["ds"],
                    y=forecast["yhat"],
                    mode="lines+markers",
                    name="Predicted Values",
                    line=dict(color='rgb(151, 51, 30)', width=2)
                )
            
                fig1=go.Figure()
                fig1.add_trace(trace1)
                fig1.add_trace(trace2)

                fig1['layout'].update(height = 500, width = 900, title = "Forecasted Vs Actual Values")
                st.plotly_chart(fig1)
            
            elif test_upload is None:
                st.error("NO TEST DATA UPLOADED.")
                
                
            



    if upload is not None:
        
        if launch and filter_button:

            st.subheader("2. Metrics")

            if forecast_button and ( (len(regressors)>0 and test_upload is not None) or (len(regressors)==0 and not upload_test_data) or (len(regressors)==0 and upload_test_data and test_upload is not None) ):
                

                if cross_validation_:
                    
                    arr=df_cv["cutoff"].unique()
                    metric_df=pd.DataFrame(columns=[f"cv_{j}" for j in range(1,cv+1)])

                    for i,k in enumerate(arr):
                        temp=df_cv.loc[df_cv["cutoff"]==k]
                        
                        mae_value=round(mean_absolute_error(temp["y"].values, temp["yhat"].values), 2)
                        rmse_value=round(mean_squared_error(temp["y"].values, temp["yhat"].values)**0.5, 2)
                        mdape_value=calculate_mdape(temp["y"].values, temp["yhat"].values)
                        smape_value=calculate_smape(temp["y"].values, temp["yhat"].values)

                        metric_df[f"cv_{i+1}"]=np.array([smape_value, mdape_value, rmse_value, mae_value])

                    metric_df["METRIC"]=["SMAPE", "MDAPE", "RMSE", "MAE"]
                    metric_df.set_index(keys="METRIC", inplace=True)

                    st.dataframe(metric_df)


                    smape_avg=round(metric_df.loc["SMAPE",:].mean(), 2)
                    mdape_avg=round(metric_df.loc["MDAPE",:].mean(), 2)
                    rmse_avg=round(metric_df.loc["RMSE",:].mean(), 2)
                    mae_avg=round(metric_df.loc["MAE",:].mean(), 2)

                    smape, mdape, rmse, mae=st.columns(4)

                    smape.metric("**:red[AVG SMAPE]**", f"{smape_avg}%")
                    mdape.metric("**:red[AVG MDAPE]**", f"{mdape_avg}%")
                    rmse.metric("**:red[AVG RMSE]**", f"{rmse_avg}")
                    mae.metric("**:red[AVG MAE]**", f"{mae_avg}")

                
                else:

                    y_true=df["y"]
                    y_pred=forecast.iloc[:df["ds"].count()]["yhat"]
                    rmse_value=round(mean_squared_error(y_true, y_pred)**0.5, 2)
                    mae_value=round(mean_absolute_error(y_true, y_pred), 2)
                    mdape_value=calculate_mdape(y_true, y_pred)
                    smape_value=calculate_smape(y_true, y_pred)

                    smape,mdape,mae,rmse=st.columns(4,gap='small')

                    smape.metric("**:red[SMAPE]**", f"{smape_value}%")
                    mdape.metric(f"**:red[MDAPE]**", f"{mdape_value}%")
                    rmse.metric(f"**:red[RMSE]**", f"{rmse_value}")
                    mae.metric(f"**:red[MAE]**" , f"{mae_value}")


            elif not forecast_button:


                if cross_validation_:

                    arr=df_cv["cutoff"].unique()
                    metric_df=pd.DataFrame(columns=[f"cv_{j}" for j in range(1,cv+1)])

                    for i,k in enumerate(arr):
                        temp=df_cv.loc[df_cv["cutoff"]==k]
                        
                        mae_value=round(mean_absolute_error(temp["y"].values, temp["yhat"].values), 2)
                        rmse_value=round(mean_squared_error(temp["y"].values, temp["yhat"].values)**0.5, 2)
                        mdape_value=calculate_mdape(temp["y"].values, temp["yhat"].values)
                        smape_value=calculate_smape(temp["y"].values, temp["yhat"].values)

                        metric_df[f"cv_{i+1}"]=np.array([smape_value, mdape_value, rmse_value, mae_value])

                    metric_df["METRIC"]=["SMAPE", "MDAPE", "RMSE", "MAE"]
                    metric_df.set_index(keys="METRIC", inplace=True)

                    st.dataframe(metric_df)


                    smape_avg=round(metric_df.loc["SMAPE",:].mean(), 2)
                    mdape_avg=round(metric_df.loc["MDAPE",:].mean(), 2)
                    rmse_avg=round(metric_df.loc["RMSE",:].mean(), 2)
                    mae_avg=round(metric_df.loc["MAE",:].mean(), 2)

                    smape, mdape, rmse, mae=st.columns(4)

                    smape.metric("**:red[AVG SMAPE]**", f"{smape_avg}%")
                    mdape.metric("**:red[AVG MDAPE]**", f"{mdape_avg}%")
                    rmse.metric("**:red[AVG RMSE]**", f"{rmse_avg}")
                    mae.metric("**:red[AVG MAE]**", f"{mae_avg}")


                else:
                
                    y_true_test=df.iloc[int(df["ds"].count()*(1-test_size)):]["y"].values
                    y_pred_test=forecast.iloc[int(df["ds"].count()*(1-test_size)):]["yhat"].values
                    y_true_train=df.iloc[:int(df["ds"].count()*(1-test_size))]["y"].values
                    y_pred_train=forecast.iloc[:int(df["ds"].count()*(1-test_size))]["yhat"].values
                    y_true_whole=df["y"].values
                    y_pred_whole=forecast["yhat"].values

                    if len(y_true_test)>0:
                        evaluation_type=st.radio("**How to Evaluate Metrics ?**", options=["Get Metrics Value only on Test/Validation Data", "Get Metrics Value only on Training Data", "Get Metrics Value on Whole Data"])
                    else:
                        evaluation_type=st.radio("**How to Evaluate Metrics ?**", options=["Get Metrics Value only on Training Data", "Get Metrics Value on Whole Data"])

                    smape,mdape,mae,rmse=st.columns(4,gap='small')
                    

                    if evaluation_type=="Get Metrics Value only on Test/Validation Data" and len(y_true_test)>0: # If test_size is 0 then y_true_test and y_pred_test will be empty array and mean_squared_error function will give error, so we are also checking size of y_true_test
                        rmse_value=round(mean_squared_error(y_true_test, y_pred_test)**0.5, 2)
                        mae_value=round(mean_absolute_error(y_true_test, y_pred_test), 2)
                        mdape_value=calculate_mdape(y_true_test, y_pred_test)
                        smape_value=calculate_smape(y_true_test, y_pred_test)

                    
                    elif evaluation_type=="Get Metrics Value on Whole Data":

                        rmse_value=round(mean_squared_error(y_true_whole, y_pred_whole)**0.5, 2)
                        mae_value=round(mean_absolute_error(y_true_whole, y_pred_whole), 2)
                        mdape_value=calculate_mdape(y_true_whole, y_pred_whole)
                        smape_value=calculate_smape(y_true_whole, y_pred_whole)

                    
                    elif evaluation_type=="Get Metrics Value only on Training Data":
                        
                        rmse_value=round(mean_squared_error(y_true_train, y_pred_train)**0.5, 2)
                        mae_value=round(mean_absolute_error(y_true_train, y_pred_train), 2)
                        mdape_value=calculate_mdape(y_true_train, y_pred_train)
                        smape_value=calculate_smape(y_true_train, y_pred_train)


                    smape.metric("**:red[SMAPE]**", f"{smape_value}%")
                    mdape.metric(f"**:red[MDAPE]**", f"{mdape_value}%")
                    rmse.metric(f"**:red[RMSE]**", f"{rmse_value}")
                    mae.metric(f"**:red[MAE]**" , f"{mae_value}")




    if upload is not None:
        
        if launch and filter_button:

            st.subheader("3. Components of the Forecast")


            if forecast_button and ( (len(regressors)>0 and test_upload is not None) or (len(regressors)==0 and not upload_test_data) or (len(regressors)==0 and upload_test_data and test_upload is not None) ):
                show_components=True
            elif not forecast_button:
                show_components=True
            else:
                show_components=False


            if show_components:

                # Trend Component of Model

                trace_trend_lower=go.Scatter(
                    x=forecast["ds"],
                    y=forecast["trend_lower"],
                    mode="lines",
                    name="Lower_Trend",
                    line=dict(color='rgb(244, 24, 231)', width=2)
                )
                trace_trend_upper=go.Scatter(
                    x=forecast["ds"],
                    y=forecast["trend_upper"],
                    mode="lines",
                    name="Upper_Trend",
                    fill='tonexty',
                    line_color="indigo"
                )
                fig2=go.Figure()
                fig2.add_trace(trace_trend_lower)
                fig2.add_trace(trace_trend_upper)
                fig2['layout'].update(height = 350, width = 750, title = "Trend")
                st.plotly_chart(fig2)
                


                # Seasonality Component of Model

                if add_custom_seasonality:
                    trace_custom_seasonality=go.Scatter(
                        x=forecast["ds"],
                        y=forecast[name_c],
                        mode="lines",
                        name=name_c,
                        fill="tozeroy"
                    )
                    fig3=go.Figure()
                    fig3.add_trace(trace_custom_seasonality)
                    fig3['layout'].update(height = 350, width = 750, title = name_c)
                    st.plotly_chart(fig3)
                

                if weekly_seasonality=="Custom":
                    trace_weekly_seasonality=go.Scatter(
                        x=forecast["ds"],
                        y=forecast["Weekly_Seasonality"],
                        mode="lines",
                        name="Weekly_Seasonality",
                        fill="tozeroy"
                    )
                    fig4=go.Figure()
                    fig4.add_trace(trace_weekly_seasonality)
                    fig4['layout'].update(height = 350, width = 750, title = "Weekly_Seasonality")
                    st.plotly_chart(fig4)

                elif weekly_seasonality=="auto" and "weekly" in forecast.columns.to_list():
                    trace_weekly_seasonality=go.Scatter(
                        x=forecast["ds"],
                        y=forecast["weekly"],
                        mode="lines",
                        name="Weekly_Seasonality",
                        fill="tozeroy"
                    )
                    fig4=go.Figure()
                    fig4.add_trace(trace_weekly_seasonality)
                    fig4['layout'].update(height = 350, width = 750, title = "Weekly_Seasonality")
                    st.plotly_chart(fig4)

                

                if yearly_seasonality=="Custom":
                    trace_yearly_seasonality=go.Scatter(
                        x=forecast["ds"],
                        y=forecast["Yearly_Seasonality"],
                        mode="lines",
                        name="Yearly_Seasonality",
                        fill="tozeroy"
                    )
                    fig5=go.Figure()
                    fig5.add_trace(trace_yearly_seasonality)
                    fig5['layout'].update(height = 350, width = 750, title = "Yearly_Seasonality")
                    st.plotly_chart(fig5)

                elif yearly_seasonality=="auto" and "yearly" in forecast.columns.to_list():
                    trace_yearly_seasonality=go.Scatter(
                        x=forecast["ds"],
                        y=forecast["yearly"],
                        mode="lines",
                        name="Yearly_Seasonality",
                        fill="tozeroy"
                    )
                    fig5=go.Figure()
                    fig5.add_trace(trace_yearly_seasonality)
                    fig5['layout'].update(height = 350, width = 750, title = "Yearly_Seasonality")
                    st.plotly_chart(fig5)


                # Effect of Regressors.
                if len(regressors)>0:
                    df_regressors_coef=regressor_coefficients(model)

                    trace_regressors=go.Bar(
                        x=df_regressors_coef["regressor"],
                        y=df_regressors_coef["coef"],
                        name="Effect of Regressors added in Forecast"
                    )

                    fig_regressors=go.Figure()
                    fig_regressors.add_trace(trace_regressors)
                    st.plotly_chart(fig_regressors)

                    
    if upload is not None:

        if launch and filter_button:

            if forecast_button and ( (len(regressors)>0 and test_upload is not None) or (len(regressors)==0 and not upload_test_data) or (len(regressors)==0 and upload_test_data and test_upload is not None) ):
                download=True
            elif not forecast_button:
                download=True
            else:
                download=False
            
            if download:

                csv = convert_df(forecast[["ds","yhat","yhat_lower","yhat_upper"]])
                st.download_button("Download Forecasted Values", csv, file_name="forecasted_values.csv", mime='text/csv')





###                                                  CODE FOR LSTMs
########################################################################################################################################
########################################################################################################################################
########################################################################################################################################


elif algo=="LSTMs":



    ####################################################################################################################################
    
    # TAKING INPUT FROM USER (INPUT SPECIFIC TO LSTM MODEL)

    #######################################################################################################################################

    st.sidebar.header("2. MODELLING")

    with st.sidebar.expander("LSTM Architecture"):
        
        input_steps=st.number_input(label="Number of Sequences in a Single Input", min_value=1, step=1, value=4, help="Number of Time Steps that should be used as a single Input.  \nIf kept 7 Days then it means that every 'y' value depends on Input from Previous 7 Days.")
        output_steps=st.number_input(label="Number of Sequences in a Single Output", min_value=1, step=1, value=1, help="Number of Time Steps for which LSTM should Predict values using a Single Input.  \nIf kept 7 Days then it means that every 'y' will have values for next 7 Days.")
        layers=st.number_input(label="Number of LSTM Layers", min_value=1, step=1, value=1, help="Number of Stacked LSTM Layers in the Architecture.  \nMore Layers means the Model can learn a More Complicated function.  \nLarge number of Layers can also cause Overfitting.")
        
        for i in range(layers):
            st.number_input(label=f"Dimension of Cell State/Hidden State for Layer {i+1}", min_value=1, step=1, value=2, key=f"layer_{i}_CellState")

        epochs=st.number_input(label="Number of Epochs for Training", min_value=10, max_value=2000, value=100, step=10)

        st.write("One ***Dense Layer*** will be Present at end of last LSTM Layer.  \n***Adam Optimizer*** is used along with ***Mean Squared Error*** as the Loss Function.")



    with st.sidebar.expander("Activations for LSTM Layers"):

        activation=st.selectbox("Activation for Hidden States",options=["tanh","relu","sigmoid","linear"], help="The activation argument applies to the candidate hidden state and output hidden state.  \nThe default value for this argument is a hyperbolic tangent function.")
        recurrent_activation=st.selectbox("Activation for Input,Forget,Output Gates", options=["sigmoid","relu","tanh","linear"], help="The recurrent_activation argument applies to the input, forget, and output gates.  \nThe default value for this argument is a hard-sigmoid function.")



    with st.sidebar.expander("Date-Time Features"):

        if freq_unit=="hours":
            lst_features=st.multiselect(label="Features to Add", options=["year","month","week","day","hour"])

        elif freq_unit=="minutes":
            lst_features=st.multiselect(label="Features to Add", options=["year","month","week","day","hour","minute"])

        elif freq_unit=="seconds":
            lst_features=st.multiselect(label="Features to Add", options=["year","month","week","day","hour","minute","second"])

        elif freq_unit=="days":
            lst_features=st.multiselect(label="Features to Add", options=["year","month","week","day"])
        
        else:
            lst_features=st.multiselect(label="Features to Add", options=["year","month","week"])
        
        

        

    # Parameters that help in Model Evaluation.(Train test Splitting or Cross Validation)  
    if upload is not None:
        st.sidebar.header("3. MODEL EVALUATION")

    with st.sidebar.expander("Train/Validation Splitting Or Cross Validation"):

        if upload is not None:

            cross_validation_=st.checkbox("Perform Cross Validation", value=False, help="Check to evaluate performance through a cross-validation, or uncheck to use a simple training/test split.") # Checkbox for performing Cross Validation or doing Simple Train-Test Split.

            if cross_validation_:
                cv=st.number_input("Number of CV Folds", value=5, min_value=2, help="Number of distinct training/validation pairs to include in the Cross-Validation.")
                test_size=0

            else:   # If the user doesn't opts for Cross_Validation then he/she has to mention the test_size for the data Uploaded. 
                test_size=st.number_input("Test Size in Percentage of Total Data", value=20.0, min_value=0.0, max_value=100.0)*0.01 # The user should Input the Test Size as percentage of size of dataset Uploaded.




    if upload is not None:
        forecast_button=st.sidebar.checkbox("Make Forecast for Future Dates", value=False) 
        # If the User wants to get the forecast on Future dates (Which are not there in the initial Uploaded Dataset), then he/she has to check the 'forecast_button'.
        # If the 'forecast_button' is checked by the the user, then whole of the data uploaded by the user will be used for Training the Model and error/metrics will be calculated only on Training Data.


    if upload is not None and forecast_button:
        st.sidebar.header("4. MAKE FORECAST")

    with st.sidebar.expander("Forecasting on Future Dates",expanded=True):

        if upload is not None and forecast_button:

            if len(num_cols)>0:

                st.write("Upload Test Data CSV file having the same Schema as the Training data CSV file.")
                test_upload=st.file_uploader("Upload Test Data", type={"csv"})

                if test_upload is not None:
                    test_data=pd.read_csv(test_upload, index_col=0) # There should be one index like column in data other than Date and other important columns.
                    test_data2=test_data.copy()

            else:

                upload_test_data=st.checkbox("Upload Test Data")

                if upload_test_data:

                    st.write("Upload Test Data CSV file having the same Schema as the Training data CSV file.")
                    test_upload=st.file_uploader("Upload Test Data", type={"csv"})


                    if test_upload is not None:
                        test_data=pd.read_csv(test_upload,index_col=0) # There should be one 'index like column' in data other than Date and other important columns. 'index_col=0' makes the first column of data as the 'index'. 
                        test_data2=test_data.copy()
                
                else:

                    future_forecast_period=st.number_input("Future Forecast Period", help="Number of Future Dates on which Forecast is to be made", min_value=input_steps, value=input_steps)

                     



    ##########################################################################################################################


    # MODIFYING DATA AND TRAINING MODEL BASED ON USER INPUT

    #############################################################################################################################
        

    ## Modifying 'df' dataframe. All the filters and modifications that are specified in "Filtering Data" and "Info About Data"
    if upload is not None:          # Checking if File is uploaded or not, If Something is Uploaded then only the "if" condition gets satisfied.
        if filter_button:           # If checkbox of Filter button is pressed, then only this 'if' condition gets satisfied and all filtering/processing of Uploaded dataset takes place.

            df[date_column]=pd.to_datetime(df[date_column], format=date_format) # Changing Data Type of Date Column to DateTime.
            dates=df[date_column].unique()

            for i in cat_cols:      # This loop iterates for all column names present in 'cat_cols' multiselect object and checks whether the checkbox corresponding to the particular column is checked or not.  
                if not st.session_state[i] and len(st.session_state[i+'m'])>0:  # If the checkbox (present in 'col_list') corresponding to a column name (present in 'cat_cols') is unchecked and there are more than 0 values in the multiselect object (made as the checkbox for that column was unchecked) corresponding to that column, then we filter the dataset using the values mentioned in that multiselect object.
                    df=df.loc[df[i].isin(st.session_state[i+'m'])]


            agg_funcs_for_num_cols=[st.session_state[col+" agg"] for col in num_cols] # Making a list of aggregation functions for each column mentioned in 'num_cols' object.
            diction=dict(zip(num_cols,agg_funcs_for_num_cols))                        # Making a dictionary that contains column name (present in 'num_cols') as key and its aggregation function (present in 'agg_funcs_for_num_cols') as its value.

            

            dates_present_after_filter=df[date_column].unique()

            if set(dates)!=set(dates_present_after_filter):

                filtered_out_dates=pd.DataFrame({date_column:[date for date in dates if date not in dates_present_after_filter]})
                if len(diction)>0:
                    aggregations=df.agg(diction)
                df=pd.concat([df,filtered_out_dates], ignore_index=True)

                for col in num_cols:
                    df[col].replace(np.nan, aggregations.loc[col], inplace=True)
                df[target_column].replace(np.nan, 0, inplace=True)
            
            

            diction[target_column]=y_variable_agg_func               # Adding a new key-value pair in the 'diction' dictionary, the new key-value pair is of y_variable and its aggregation function.

            df=df.groupby([date_column]).agg(diction).reset_index()  # This groups the data according to Date column and thus now we get one y value for one Date value, therefore only 1 Time Series.

            df.rename(columns={str(date_column): "ds", str(target_column):"y"}, inplace=True) # Just changing name of Date and target column to "ds" and "y" as its needed for Training of Prophet Model.
            

            # This Code adds Date-Time Features to the Data.
            for time in lst_features:
                if time=="year":
                    df["_year_"]=df["ds"].apply(lambda x:x.year)
                elif time=="month":
                    df["_month_"]=df["ds"].apply(lambda x:x.month)
                elif time=="week":
                    df["_week_"]=df["ds"].apply(lambda x:x.week)
                elif time=="day":
                    df["_day_"]=df["ds"].apply(lambda x:x.day)
                elif time=="hour":
                    df["_hour_"]=df["ds"].apply(lambda x:x.hour)
                elif time=="minute":
                    df["_minute_"]=df["ds"].apply(lambda x:x.minute)
                elif time=="second":
                    df["_second_"]=df["ds"].apply(lambda x:x.second)
                


            # Below code just moves the "target variable" column to the end, as the "target variable" should be the last column. (This will help in further data preparation) 
            lst=df.columns.to_list() 
            lst.remove("y")
            lst.append("y")
            df=df[lst]

        
            st.write("#")
            st.write("#")
            st.write("#")

            st.table(df.head())
            st.write(f'<p style="font-size:26px;">Uploaded data has {df["ds"].nunique()} unique Date Values</p>', unsafe_allow_html=True)


            df_filtered=df.copy() # A Copy of filtered df-dataframe will be needed further.
            df["ds"]=df["ds"].apply(lambda x:x.year*10000 + x.month*100 + x.day) # This is done to convert dtype of "ds" column from "datetime" to "int" so that Feature Scaling can take place inside "prepare_data_LSTM" function.

            st.table(df.head())

            # Breaking Data into X and y for Training LSTM Model
            X,y,scaler_X,scaler_Y=prepare_data_LSTM(df, input_steps, output_steps)

            X=X[:,:,1:] # To Remove 'ds' Column
            

        else:  # This 'else' section is to restore the processed/filtered dataset to its original uploaded form when we uncheck the 'filter_button'.
            df=df2

    
    # Modifying test_data uploaded by user (In the same Format as the training data was modified as above)
    if upload is not None:

        if forecast_button:

            if len(num_cols)>0 or upload_test_data:

                if test_upload is not None:

                    if filter_button:
                    
                        test_data[date_column]=pd.to_datetime(test_data[date_column], format=date_format)
                        test_dates=test_data[date_column].unique()
                        

                        for i in cat_cols:      # This loop iterates for all column names present in 'cat_cols' multiselect object and checks whether the checkbox corresponding to the particular column is checked or not.  
                            if not st.session_state[i] and len(st.session_state[i+'m'])>0:  # If the checkbox (present in 'col_list') corresponding to a column name (present in 'cat_cols') is unchecked and there are more than 0 values in the multiselect object (made as the checkbox for that column was unchecked) corresponding to that column, then we filter the dataset using the values mentioned in that multiselect object.
                                test_data=test_data.loc[test_data[i].isin(st.session_state[i+'m'])] 

                        agg_funcs_for_num_cols_forecast=[st.session_state[col+" agg"] for col in num_cols] # Making a list of aggregation functions for each column mentioned in 'num_cols' object.
                        diction_forecast=dict(zip(num_cols, agg_funcs_for_num_cols_forecast))              # Making a dictionary that contains column name (present in 'num_cols') as key and its aggregation function (present in 'agg_funcs_for_num_cols') as its value. 



                        test_dates_present_after_filter=test_data[date_column].unique()

                        if set(test_dates)!=set(test_dates_present_after_filter):

                            filtered_out_test_dates=pd.DataFrame({date_column:[date for date in test_dates if date not in test_dates_present_after_filter]})
                            if len(diction_forecast)>0:
                                aggregations=test_data.agg(diction_forecast)
                            test_data=pd.concat([test_data, filtered_out_test_dates], ignore_index=True)

                            for col in num_cols:
                                test_data[col].replace(np.nan, aggregations.loc[col], inplace=True)

                        
                        if len(diction_forecast)>0:
                            test_data=test_data.groupby([date_column]).agg(diction_forecast).reset_index()  # This groups the data according to Date column and thus now we get one y value for one Date value, therefore only 1 Time Series.
                        else: ## Adding this else statement ensures that even if len(diction_forecast)==0, the test_data will be finally having no repeated date values.
                            test_data.drop_duplicates(subset=date_column,inplace=True, ignore_index=True)
                            test_data=test_data[[date_column]]

                        test_data.rename(columns={str(date_column): "ds"}, inplace=True) # Just changing name of Date and target column to "ds" and "y" as its needed for Training of Prophet Model.



                        # This Code adds Date-Time Features to the Test-Data.
                        for time in lst_features:
                            if time=="year":
                                test_data["_year_"]=test_data["ds"].apply(lambda x:x.year)
                            elif time=="month":
                                test_data["_month_"]=test_data["ds"].apply(lambda x:x.month)
                            elif time=="week":
                                test_data["_week_"]=test_data["ds"].apply(lambda x:x.week)
                            elif time=="day":
                                test_data["_day_"]=test_data["ds"].apply(lambda x:x.day)
                            elif time=="hour":
                                test_data["_hour_"]=test_data["ds"].apply(lambda x:x.hour)
                            elif time=="minute":
                                test_data["_minute_"]=test_data["ds"].apply(lambda x:x.minute)
                            elif time=="second":
                                test_data["_second_"]=test_data["ds"].apply(lambda x:x.second)
                            

                        test_data_filtered=test_data.copy()
                        test_data["ds"]=test_data["ds"].apply(lambda x:x.year*10000 + x.month*100 + x.day) # This is done to convert dtype of "ds" column from "datetime" to "int" so that Feature Scaling can take place inside "prepare_data_LSTM" function.

                        st.table(test_data.head()) ####################

                        # Breaking Data into X and y for Training LSTM Model
                        X_test=prepare_test_data_LSTM(test_data, input_steps, output_steps, scaler_X)


                    else:  # This 'else' section is to restore the processed/filtered dataset to its original uploaded form when we uncheck the 'filter_button'.
                        test_data=test_data2

                   
            else: # If User doesn't Uploads test Data but wants the Future Forecast on some dates then this 'else' statement executes.
                
                if filter_button:
                    
                    start_date=df_filtered.iloc[-1,0] + pd.Timedelta(value=freq, unit=freq_unit) # Taking the Last Date + 1 time unit as the Start Date of Forecasting Period.
                    test_data=pd.DataFrame(pd.date_range(start=start_date, periods=future_forecast_period, freq=pd.Timedelta(value=freq,unit=freq_unit)), columns=["ds"])


                    # This Code adds Date-Time Features to the Test-Data.
                    for time in lst_features:
                        if time=="year":
                            test_data["_year_"]=test_data["ds"].apply(lambda x:x.year)
                        elif time=="month":
                            test_data["_month_"]=test_data["ds"].apply(lambda x:x.month)
                        elif time=="week":
                            test_data["_week_"]=test_data["ds"].apply(lambda x:x.week)
                        elif time=="day":
                            test_data["_day_"]=test_data["ds"].apply(lambda x:x.day)
                        elif time=="hour":
                            test_data["_hour_"]=test_data["ds"].apply(lambda x:x.hour)
                        elif time=="minute":
                            test_data["_minute_"]=test_data["ds"].apply(lambda x:x.minute)
                        elif time=="second":
                            test_data["_second_"]=test_data["ds"].apply(lambda x:x.second)

                    
                    test_data_filtered=test_data.copy()
                    test_data["ds"]=test_data["ds"].apply(lambda x:x.year*10000 + x.month*100 + x.day) # This is done to convert dtype of "ds" column from "datetime" to "int" so that Feature Scaling can take place inside "prepare_data_LSTM" function.
                    X_test=prepare_test_data_LSTM(test_data, input_steps, output_steps, scaler_X)
                    print(X_test)


        # Building the Architecture of LSTM and Training Model as per parameters given by User.
        launch=st.checkbox("Launch Model",value=True if default_data else False, help="Check to launch forecast. A new forecast will be made each time some parameter is changed in the sidebar.")

        if launch and filter_button:
            
            model=build_model(layers,activation,recurrent_activation,input_steps,X.shape[2],output_steps) # This builds the Architecture of the Model based on User Inputs.
            
            if forecast_button:

                if cross_validation_:

                    model_ = KerasRegressor(model=model, epochs=epochs)
                    kfold = KFold(n_splits=cv)

                    smape=[]
                    mdape=[]
                    rmse=[]
                    mae=[]

                    # Performing Cross Validation and Calculating Error Metrics
                    for fold_n, (train_idx, test_idx) in enumerate(kfold.split(X, y)):
                        X_train, y_train = X[train_idx], y[train_idx]
                        X_test_, y_test = X[test_idx], y[test_idx]
                        model_.fit(X=X_train, y=y_train)
                        y_pred=model_.predict(X_test_)
                        y_pred=scaler_Y.inverse_transform(y_pred)
                        y_test=scaler_Y.inverse_transform(y_test)

                        smape.append(calculate_smape(np.array(y_test),np.array(y_pred)))
                        mdape.append(calculate_mdape(np.array(y_test),np.array(y_pred)))
                        mae.append(round(mean_absolute_error(np.array(y_test), np.array(y_pred)), 2))
                        rmse.append(round(mean_squared_error(np.array(y_test), np.array(y_pred))**0.5, 2))
                    
                    avg_rmse=np.array(rmse).mean()
                    avg_mae=np.array(mae).mean()
                    avg_smape=np.array(smape).mean()
                    avg_mdape=np.array(mdape).mean()


                
                model.fit(x=X, y=y, epochs=epochs, shuffle=True)

                y_predicted=recursive_forecasting(model,X,X_test,output_steps,input_steps)
                y_forecast=scaler_Y.inverse_transform(y_predicted.reshape(-1,1))
                y_forecast=y_forecast.ravel()
    

            else:

                if cross_validation_:

                    model = KerasRegressor(model=model, epochs=epochs)
                    kfold = KFold(n_splits=cv)

                    smape=[]
                    mdape=[]
                    rmse=[]
                    mae=[]

                    # Performing Cross Validation and Calculating Error Metrics
                    for fold_n, (train_idx, test_idx) in enumerate(kfold.split(X, y)):
                        X_train, y_train = X[train_idx], y[train_idx]
                        X_test_, y_test = X[test_idx], y[test_idx]
                        model.fit(X=X_train, y=y_train)
                        y_pred=model.predict(X_test_)
                        y_pred=scaler_Y.inverse_transform(y_pred)
                        y_test=scaler_Y.inverse_transform(y_test)

                        smape.append(calculate_smape(np.array(y_test),np.array(y_pred)))
                        mdape.append(calculate_mdape(np.array(y_test),np.array(y_pred)))
                        mae.append(round(mean_absolute_error(np.array(y_test), np.array(y_pred)), 2))
                        rmse.append(round(mean_squared_error(np.array(y_test), np.array(y_pred))**0.5, 2))
                    
                    avg_rmse=np.array(rmse).mean()
                    avg_mae=np.array(mae).mean()
                    avg_smape=np.array(smape).mean()
                    avg_mdape=np.array(mdape).mean()
                    
                else:
                    
                    # X_train, X_test_, y_train, y_test = train_test_split(X, y, test_size=test_size, random_state=42)
                    X_train, y_train=X[:int(len(X)*test_size)+1], y[:int(len(y)*test_size)+1]
                    X_test_, y_test=X[int(len(X)*test_size)+1:], y[int(len(y)*test_size)+1:]
                    
                    model.fit(x=X_train, y=y_train, epochs=epochs, shuffle=True)
                    y_pred=model.predict(X_test_)

                    print(y_train)
                    print(y_test)

                    y_test=np.concatenate((y_test[:-1,0],y_test[-1:].reshape(-1)))
                    y_pred=np.concatenate((y_pred[:-1,0],y_pred[-1:].reshape(-1)))
                    y_train=np.concatenate((y_train[:-1,0],y_train[-1:].reshape(-1)))


                    y_pred=scaler_Y.inverse_transform(y_pred.reshape(-1,1))
                    y_test=scaler_Y.inverse_transform(y_test.reshape(-1,1))
                    y_train=scaler_Y.inverse_transform(y_train.reshape(-1,1))
                    
                    rmse_value=round(mean_squared_error(np.array(y_test), np.array(y_pred))**0.5, 2)
                    mae_value=round(mean_absolute_error(np.array(y_test), np.array(y_pred)), 2)
                    smape_value=calculate_smape(np.array(y_test),np.array(y_pred))
                    mdape_value=calculate_mdape(np.array(y_test),np.array(y_pred))


    ######################################################################################################################################


    # OUTPUT DISPLAYED TO THE USER BASED ON HIS/HER INPUT. DISPLAYES THE FORESCAST/HOW THE MODEL PERFORMED.

    ######################################################################################################################################


    if upload is not None:

        if filter_button and launch:

            st.subheader("1. Overview")

            if forecast_button:

                trace1=go.Scatter(
                    x=df_filtered["ds"],
                    # x=pd.concat((df_filtered["ds"],test_data_filtered["ds"]),ignore_index=True)
                    y=df_filtered["y"],
                    mode="lines",
                    name="Actual Value",
                    line=dict(color='rgb(244, 24, 231)', width=2)
                )

                trace2=go.Scatter(
                    x=test_data_filtered["ds"],
                    y=y_forecast,
                    mode="lines+markers",
                    name="Forecasted Values on Future Dates",
                    line=dict(color='rgb(20, 161, 10)', width=2)
                )
                
                fig1=go.Figure()
                fig1.add_trace(trace1)
                fig1.add_trace(trace2)
                # fig1.add_trace(trace3)

                fig1['layout'].update(height = 500, width = 900, title = "Forecasted Vs Actual Values")
                st.plotly_chart(fig1)
            

            elif not cross_validation_:

                trace1=go.Scatter(
                    x=df_filtered.loc[:,"ds"].iloc[:len(y_train)],
                    # x=pd.concat((df_filtered["ds"],test_data_filtered["ds"]),ignore_index=True)
                    y=y_train,
                    mode="lines",
                    name="Actual Value",
                    line=dict(color='rgb(244, 24, 231)', width=2)
                )

                fig1=go.Figure()
                fig1.add_trace(trace1)

                fig1['layout'].update(height = 500, width = 900, title = "Forecasted Vs Actual Values")
                st.plotly_chart(fig1)



            




















