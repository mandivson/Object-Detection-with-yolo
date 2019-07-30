#!/usr/bin/env python3
from flask import Flask
from flask import render_template
from flask import request
from flask import redirect
from flask import url_for
from flask import flash
from flask import jsonify
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from database_setup import Base, Restaurant, MenuItem, User, Cart


# New imports for this step
from flask import session as login_session
import random
import string

from oauth2client.client import flow_from_clientsecrets
from oauth2client.client import FlowExchangeError
import httplib2
import json
from flask import make_response
import requests

app = Flask(__name__)

CLIENT_ID = json.loads(
    open('client_secrets.json', 'r').read())['web']['client_id']
APPLICATION_NAME = "Restaurant Application"

engine = create_engine('sqlite:///restaurant.db',
                       connect_args={'check_same_thread': False}, echo=True)
Base.metadata.bind = engine

DBSession = sessionmaker(bind=engine)
session = DBSession()


# ******************** Create anti-forgery state token***********************
@app.route('/login/')
def showLogin():
    state = ''.join(random.choice(string.ascii_uppercase + string.digits)
                    for x in xrange(32))
    login_session['state'] = state
    # return "The current session state is %s" % login_session['state']
    return render_template('login.html',  STATE=state)

# ***********************Google Login**************************************


@app.route('/gconnect', methods=['POST'])
def gconnect():
    # Validate state token
    if request.args.get('state') != login_session['state']:
        response = make_response(json.dumps('Invalid state parameter.'), 401)
        response.headers['Content-Type'] = 'application/json'
        return response
    # Obtain authorization code
    code = request.data

    try:
        # Upgrade the authorization code into a credentials object
        oauth_flow = flow_from_clientsecrets('client_secrets.json', scope='')
        oauth_flow.redirect_uri = 'postmessage'
        credentials = oauth_flow.step2_exchange(code)
    except FlowExchangeError:
        response = make_response(json.dumps('Failed to upgrade'
                                            ' the authorization code.'), 401)
        response.headers['Content-Type'] = 'application/json'
        return response

    # Check that the access token is valid.
    access_token = credentials.access_token
    url = ('https://www.googleapis.com/oauth2/v1/tokeninfo?'
           'access_token=%s' % access_token)
    h = httplib2.Http()
    result = json.loads(h.request(url, 'GET')[1])
    # If there was an error in the access token info, abort.
    if result.get('error') is not None:
        response = make_response(json.dumps(result.get('error')), 500)
        response.headers['Content-Type'] = 'application/json'
        return response

    # Verify that the access token is used for the intended user.
    gplus_id = credentials.id_token['sub']
    if result['user_id'] != gplus_id:
        response = make_response(json.dumps("Token's user ID doesn't match"
                                            " given user ID."), 401)
        response.headers['Content-Type'] = 'application/json'
        return response

    # Verify that the access token is valid for this app.
    if result['issued_to'] != CLIENT_ID:
        response = make_response(json.dumps("Token's client ID does"
                                            " not match app's."), 401)
        print "Token's client ID does not match app's."
        response.headers['Content-Type'] = 'application/json'
        return response

    stored_access_token = login_session.get('access_token')
    stored_gplus_id = login_session.get('gplus_id')
    if stored_access_token is not None and gplus_id == stored_gplus_id:
        response = make_response(json.dumps('Current user is'
                                            ' already connected.'), 200)
        response.headers['Content-Type'] = 'application/json'
        return response

    # Store the access token in the session for later use.
    login_session['access_token'] = credentials.access_token
    login_session['gplus_id'] = gplus_id

    # Get user info
    userinfo_url = "https://www.googleapis.com/oauth2/v1/userinfo"
    params = {'access_token': credentials.access_token, 'alt': 'json'}
    answer = requests.get(userinfo_url, params=params)
    data = json.loads(answer.text)
    login_session['username'] = data["name"]
    login_session['picture'] = data["picture"]
    login_session['email'] = data["email"]

    user_id = getUserID(login_session['email'])
    if not user_id:
        user_id = createUser(login_session)
    login_session['user_id'] = user_id

    output = ''
    output += '<h1 style="text-align:center;'
    output += ' margin-top: 50px;">Login Successful!!</h1>'
    output += '<h1 style="text-align:center">Welcome, '
    output += login_session['username']
    output += '!</h1>'
    output += '<img src="'
    output += login_session['picture']
    output += ' " style = "margin-left:500px; margin-top:10px; width: 300px;'
    output += ' height: 300px;border-radius: 150px;-webkit-border-radius:'
    output += ' 150px;-moz-border-radius: 150px;"> '
    output += '<p style="text-align: center; margin-top: 50px">'
    output += 'Redirecting...</P>'
    print "done!"
    return output


@app.route('/gdisconnect')
def gdisconnect():
    access_token = login_session.get('access_token')
    if access_token is None:
        print 'Access Token is None'
        response = make_response(json.dumps('Current user Disconnected.'), 401)
        response.headers['Content-Type'] = 'application/json'
        return response
    print 'In gdisconnect access token is %s', access_token
    print 'User name is: '
    print login_session['email']
    url = 'https://accounts.google.com/o/oauth2/revoke?token=%s' % access_token
    h = httplib2.Http()
    result = h.request(url, 'GET')[0]
    print 'result is '
    print result
    if result['status'] == '200':
        del login_session['access_token']
        del login_session['gplus_id']
        del login_session['username']
        del login_session['email']
        del login_session['picture']
        response = make_response(json.dumps('Successfully disconnected.'), 200)
        response.headers['Content-Type'] = 'application/json'
        flash("Logout Successfull !!")
        return redirect(url_for('showRestaurants'))
    else:
        response = make_response(json.dumps('Failed to revoke'
                                            ' token for given user.', 400))
        response.headers['Content-Type'] = 'application/json'
        return response


# ***********************************JSON************************************

@app.route('/restaurants/<int:restaurant_id>/menu/JSON/')
def restaurantMenuJSON(restaurant_id):
    restaurant = session.query(Restaurant).filter_by(id=restaurant_id).one()
    item = session.query(MenuItem).filter_by(restaurant_id=restaurant_id).all()
    return jsonify(MenuItems=[i.serialize for i in item])


@app.route('/restaurants/<int:restaurant_id>/menu/<int:menu_id>/JSON/')
def menuItemJSON(restaurant_id, menu_id):
    menuItem = session.query(MenuItem).filter_by(id=menu_id).one()
    return jsonify(MenuItem=menuItem.serialize)


@app.route('/restaurants/JSON/')
def restaurantsJSON():
    restaurants = session.query(Restaurant).all()
    return jsonify(restaurants=[i.serialize for i in restaurants])


# *******************************RESTAURANT ITEMS**************************

@app.route('/')
@app.route('/restaurants/')
def showRestaurants():
    restaurant = session.query(Restaurant)
    uname = ''
    pic = ''
    if 'username' in login_session:
        uname = login_session['username']
        pic = login_session['picture']
        return render_template('restaurant.html',
                               restaurant=restaurant, name=uname, picture=pic)
    else:
        return render_template('publicrestaurants.html',
                               restaurant=restaurant, name=uname, picture=pic)


@app.route('/restaurants/top-rating')
def showTopRest():
    restaurant = session.query(Restaurant)
    uname = ''
    pic = ''
    flash("Top-Rating Restaurants")
    if 'username' in login_session:
        uname = login_session['username']
        pic = login_session['picture']
        return render_template('rtop-rating.html',
                               restaurant=restaurant, name=uname, picture=pic)
    else:
        return render_template('rtop-rating.html',
                               restaurant=restaurant, name=uname, picture=pic)


@app.route('/restaurants/Cuisine-Indian')
def showCuisineIndian():
    restaurant = session.query(Restaurant)
    uname = ''
    pic = ''
    flash("Indian-Cuisine Restaurants")
    if 'username' in login_session:
        uname = login_session['username']
        pic = login_session['picture']
        return render_template('rcuisineindian.html',
                               restaurant=restaurant, name=uname, picture=pic)
    else:
        return render_template('rcuisineindian.html',
                               restaurant=restaurant, name=uname, picture=pic)


@app.route('/restaurants/Cuisine-Chinese')
def showCuisineChinese():
    restaurant = session.query(Restaurant)
    uname = ''
    pic = ''
    flash("Chinese-Cuisine Restaurants")
    if 'username' in login_session:
        uname = login_session['username']
        pic = login_session['picture']
        return render_template('rcuisinechinese.html',
                               restaurant=restaurant, name=uname, picture=pic)
    else:
        return render_template('rcuisinechinese.html',
                               restaurant=restaurant, name=uname, picture=pic)


@app.route('/restaurants/Cuisine-American')
def showCuisineAmerican():
    restaurant = session.query(Restaurant)
    uname = ''
    pic = ''
    flash("American-Cuisine Restaurants")
    if 'username' in login_session:
        uname = login_session['username']
        pic = login_session['picture']
        return render_template('rcuisineamerican.html',
                               restaurant=restaurant, name=uname, picture=pic)
    else:
        return render_template('rcuisineamerican.html',
                               restaurant=restaurant, name=uname, picture=pic)


@app.route('/restaurants/new/', methods=['GET', 'POST'])
def newRestaurants():
    if 'username' not in login_session:
        return redirect('/login')
    if request.method == 'POST':
        newrestaurant = Restaurant(name=request.form['name'],
                                   user_id=login_session['user_id'])
        session.add(newrestaurant)
        session.commit()
        flash("New Restaurant Added Successfully")
        return redirect(url_for('showRestaurants'))
    else:
        return render_template('newrestaurant.html')


@app.route('/restaurants/<int:restaurant_id>/edit/', methods=['GET', 'POST'])
def editRestaurants(restaurant_id):
    if 'username' not in login_session:
        return redirect('/login')
    editedrest = session.query(Restaurant).filter_by(id=restaurant_id).one()
    if editedrest.user_id != login_session['user_id']:
        return "<script>{alert('Unauthorized');}</script>" 
    if request.method == 'POST':
        if request.form['name']:
            editedrest.name = request.form['name']
        if request.form['rating']:
            editedrest.rating = request.form['rating']
        if request.form['cuisine']:
            editedrest.cuisine = request.form['cuisine']
        session.add(editedrest)
        session.commit()
        flash("Restaurant Updated Successfully")
        return redirect(url_for('showRestaurants'))
    else:
        return render_template('editrestaurant.html',
                               restaurant_id=restaurant_id,
                               restaurant_name=editedrest)


@app.route('/restaurants/<int:restaurant_id>/delete/', methods=['GET', 'POST'])
def deleteRestaurants(restaurant_id):
    if 'username' not in login_session:
        return redirect('/login')   
    deleterest = session.query(Restaurant).filter_by(id=restaurant_id).one()
    if deleterest.user_id != login_session['user_id']:
        return "<script>{alert('Unauthorized');}</script>" 
    if request.method == 'POST':
        session.delete(deleterest)
        session.commit()
        flash("Restaurant Deleted Successfully")
        return redirect(url_for('showRestaurants'))
    else:
        return render_template('deleterestaurant.html',
                               restaurant_id=restaurant_id,
                               restaurant_name=deleterest)


# **********************************MENU ITEMS*******************************

@app.route('/restaurants/<int:restaurant_id>/menu')
def restaurantMenu(restaurant_id):
    restaurant = session.query(Restaurant).filter_by(id=restaurant_id).one()
    items = session.query(MenuItem).filter_by(restaurant_id=restaurant.id)
    uid = ''
    if 'username' in login_session:
        uid = getUserID(login_session['email'])
    creator = getUserInfo(restaurant.user_id)
    item = session.query(MenuItem).filter_by(restaurant_id=restaurant_id).all()

    if 'username' not in login_session:
        return render_template('publicmenu.html', items=item,
                               restaurant=restaurant, creator=creator)
    else:
        uname = login_session['username']
        pic = login_session['picture']
        return render_template('menu.html', items=items, restaurant=restaurant,
                               creator=creator, user_id=uid)


@app.route('/restaurant/<int:restaurant_id>/menu/new/',
           methods=['GET', 'POST'])
def newMenuItem(restaurant_id):
    if 'username' not in login_session:
        return redirect('/login')
    restaurant = session.query(Restaurant).filter_by(id=restaurant_id).one()
    if request.method == 'POST':
        newItem = MenuItem(name=request.form['name'],
                           restaurant_id=restaurant_id,
                           user_id=login_session['user_id'])
        session.add(newItem)
        session.commit()
        flash("New Restaurant Menu Created Successfully")
        return redirect(url_for('restaurantMenu', restaurant_id=restaurant_id))
    else:
        return render_template('newmenuitem.html', restaurant_id=restaurant_id)


@app.route('/restaurant/<int:restaurant_id>/menu/<int:menu_id>/edit/',
           methods=['GET', 'POST'])
def editMenuItem(restaurant_id, menu_id):
    if 'username' not in login_session:
        return redirect('/login')
    editedItem = session.query(MenuItem).filter_by(id=menu_id).one()
    if editedItem.user_id != login_session['user_id']:
        return "<script>{alert('Unauthorized');}</script>"
    restaurant = session.query(Restaurant).filter_by(id=restaurant_id).one()
    if request.method == 'POST':
        if request.form['name']:
            editedItem.name = request.form['name']
        if request.form['description']:
            editedItem.description = request.form['description']
        if request.form['price']:
            editedItem.price = request.form['price']
        session.add(editedItem)
        session.commit()
        flash("Restaurant Menu Item Updated Successfully")
        return redirect(url_for('restaurantMenu', restaurant_id=restaurant_id))
    else:
        return render_template('editmenuitem.html',
                               restaurant_id=restaurant_id,
                               menu_id=menu_id, item=editedItem)


@app.route('/restaurant/<int:restaurant_id>/menu/<int:menu_id>/delete/',
           methods=['GET', 'POST'])
def deleteMenuItem(restaurant_id, menu_id):
    if 'username' not in login_session:
        return redirect('/login')
    itemToDelete = session.query(MenuItem).filter_by(id=menu_id).one()
    if itemToDelete.user_id != login_session['user_id']:
        return "<script>{alert('Unauthorized');}</script>"
    restaurant = session.query(Restaurant).filter_by(id=restaurant_id).one()
    if request.method == 'POST':
        session.delete(itemToDelete)
        session.commit()
        flash("Restaurant Menu Deleted Successfully")
        return redirect(url_for('restaurantMenu', restaurant_id=restaurant_id))
    else:
        return render_template('deletemenuitem.html', item=itemToDelete)


# ***********************************Cart****************************************

@app.route('/cart')
def showCart():
    if 'username' not in login_session:
        return redirect('/login')
    if 'username' in login_session:
        umail = login_session['email']
        uid = getUserID(umail)
        cartitems = session.query(Cart)
        return render_template('cart.html', cart=cartitems, uid=uid)
    else:
        return redirect('/login')


@app.route('/cart/<int:menu_id>/add/')
def addToCart(menu_id):
    if 'username' not in login_session:
        return redirect('/login')
    if 'username' in login_session:
        addtocart = session.query(MenuItem).filter_by(id=menu_id).one()
        cartitems = Cart(name=addtocart.name, price=addtocart.price,
                         user_id=login_session['user_id'])
        session.add(cartitems)
        session.commit()
        flash("Item Added to Cart")
        return redirect('/cart')
    else:
        return redirect('/login')


@app.route('/cart/<int:item_id>/remove/')
def removeItemCart(item_id):
    if 'username' not in login_session:
        return redirect('/login')
    if 'username' in login_session:
        itemToDelete = session.query(Cart).filter_by(id=item_id).one()
        session.delete(itemToDelete)
        session.commit()
        flash("Item Removed Successfully")
        return redirect('/cart')
    else:
        return redirect('/login')


# **************************************CheckOut******************************

@app.route('/checkout')
def checkOut():
    if 'username' not in login_session:
        return redirect('/login')
    else:
        umail = login_session['email']
        uid = getUserID(umail)
        cartitems = session.query(Cart).filter_by(user_id=uid).all()
        for i in cartitems:
            session.delete(i)
            session.commit()
        return render_template('checkout.html',)


# ********************************User**************************************

def createUser(login_session):
    newUser = User(name=login_session['username'],
                   email=login_session['email'],
                   picture=login_session['picture'])
    session.add(newUser)
    session.commit()
    user = session.query(User).filter_by(email=login_session['email']).one()
    return user.id


def getUserInfo(user_id):
    user = session.query(User).filter_by(id=user_id).one()
    return user


def getUserID(email):
    try:
        user = session.query(User).filter_by(email=email).one()
        return user.id
    except:
        return None


if __name__ == '__main__':
    app.secret_key = 'super_secret_key'
    app.debug = True
    app.run(host='0.0.0.0', port=8000)